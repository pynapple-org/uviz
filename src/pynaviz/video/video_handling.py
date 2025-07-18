import pathlib
import threading
import time
import warnings
from contextlib import contextmanager
from typing import List, Optional, Tuple

import av
import numpy as np

# from line_profiler import profile
from numpy.typing import NDArray


def ts_to_index(ts: float, time: NDArray) -> int:
    """
    Return the index of the frame whose experimental time is just before (or equal to) `ts`.

    Parameters
    ----------
    ts : float
        Experimental timestamp to match.
    time : NDArray
        Array of experimental timestamps, assumed sorted in ascending order,
        with one entry per frame.

    Returns
    -------
    idx : int
        Index of the frame with time <= `ts`. Clipped to [0, len(time) - 1].

    Notes
    -----
    - If `ts` is smaller than all values in `time`, returns 0.
    - If `ts` is greater than all values in `time`, returns `len(time) - 1`.
    """
    idx = np.searchsorted(time, ts, side="right") - 1
    return np.clip(idx, 0, len(time) - 1)


class VideoHandler:
    """Class for getting video frames."""

    _get_from_index = False

    def __init__(
        self,
        video_path: str | pathlib.Path,
        stream_index: int = 0,
        time: Optional[NDArray] = None,
        return_frame_array: bool = True,
    ) -> None:
        self.video_path = pathlib.Path(video_path)
        self.container = av.open(video_path)
        self.stream = self.container.streams.video[stream_index]
        self.stream_index = stream_index
        self.return_frame_array = return_frame_array
        self._running = True

        # default to linspace
        # TODO : what if number of frames is 0.
        if time is None:
            self._time_provided = False
            n_frames = self.stream.frames
            frame_duration = 1 / float(self.stream.average_rate)
            self.time = np.linspace(0, frame_duration * n_frames - frame_duration, n_frames)
        else:
            # TODO : check that number of time point matches number of frames
            self._time_provided = True
            self.time = np.asarray(time)

        # initialize index for last decoded frame
        # if sampling of other signals (LFP) is much denser, multiple times the frame
        # is unchanged, so cache the idx
        self.last_loaded_idx = None

        # initialize current frame
        self.current_frame: Optional[av.VideoFrame] = None

        if self.video_path.suffix == ".mkv":
            # mkv time is rounded to 3 digits, at least in the example video
            # generated by tests/generate_numbered_video.py
            self.round_fn = lambda x: np.round(x, 3)
        else:
            self.round_fn = lambda x: x

        # These will be initialized in the thread once n_frames is known
        self.all_pts = None
        self.all_times = None
        self.key_mask = None

        self._i = 0  # write position
        self._lock = threading.Lock()
        if self.stream.frames and self.stream.frames > 0:
            self._index_thread = threading.Thread(target=self._build_index_fixed_size, daemon=True)
        else:
            self._index_thread = threading.Thread(target=self._build_index_dynamic, daemon=True)

        self._index_ready = threading.Event()
        self._index_thread.start()
        self._keypoint_pts = []
        self._pts_keypoint_ready = threading.Event()
        self._keypoint_thread = threading.Thread(target=self._extract_keypoints_pts, daemon=True)
        self._keypoint_thread.start()

    def extract_keyframe_times_and_points(
        self, video_path: str | pathlib.Path, stream_index: int = 0, first_only=False
    ) -> Tuple[NDArray, NDArray] | None:
        """
        Extract the indices and timestamps of keyframes from a video file.

        This function decodes the video while skipping non-keyframes, and records:
        - The index of each keyframe in the full video frame sequence
        - The "Presentation Time Stamp" to each keyframe.

        It is typically intended to run in a background thread during
        initialization of a ``VideoHandler``, and supports optimized seeking:

        - When the requested frame (based on experimental time) is before the
          current playback position, seeking backward is necessary.

        - When the requested frame is beyond the next known keyframe, seeking
          forward to the closest keyframe is more efficient than decoding all
          intermediate frames.

        Parameters
        ----------
        video_path : str or pathlib.Path
            The path to the video file.
        stream_index:
            The index of the video stream.
        first_only:
            If true, return the first keypoint only. Used at initialization.

        Returns
        -------
        keyframe_points : NDArray[float]
            The point number of the frame.

        keyframe_timestamps : NDArray[float]
            The timestamp of the frame.
        """
        keyframe_timestamp = []
        keyframe_pts = []

        with av.open(video_path) as container:
            stream = container.streams.video[stream_index]
            stream.codec_context.skip_frame = "NONKEY"

            frame_index = 0
            for frame in container.decode(stream):
                if not self._running:
                    return
                keyframe_timestamp.append(frame.time)
                keyframe_pts.append(frame.pts)
                if first_only:
                    break
                frame_index += 1

        return np.asarray(keyframe_pts), np.asarray(keyframe_timestamp, dtype=float)

    @contextmanager
    def _set_get_from_index(self, value):
        """Context manager for setting the shallow copy flag in a thread safe way."""
        old_value = self.__class__._get_from_index
        self.__class__._get_from_index = value
        try:
            yield
        finally:
            self.__class__._get_from_index = old_value

    def _extract_keypoints_pts(self):
        try:
            with av.open(self.video_path) as container:
                stream = container.streams.video[0]
                for packet in container.demux(stream):
                    if not self._running:
                        return
                    if packet.is_keyframe:
                        with self._lock:
                            self._keypoint_pts.append(packet.pts)
        except Exception as e:
            # do not block gui
            print("Keypoint thread error:", e)
        finally:
            self._pts_keypoint_ready.set()

    def _build_index_fixed_size(self):
        try:
            with av.open(self.video_path) as container:
                stream = container.streams.video[self.stream_index]
                n_frames = stream.frames

                if not n_frames or n_frames <= 0:
                    raise ValueError("Cannot determine total number of frames in stream.")

                self.all_pts = np.empty(n_frames, dtype=np.int64)
                self._i = 0  # Number of valid entries

                for packet in container.demux(stream):
                    if not self._running:
                        return
                    for frame in packet.decode():
                        if self._i >= n_frames:
                            break
                        with self._lock:
                            self.all_pts[self._i] = frame.pts
                            self._i += 1
        except Exception as e:
            print("Index thread error:", e)
        finally:
            self._index_ready.set()

    def _build_index_dynamic(self):
        try:
            with av.open(self.video_path) as container:
                if not self._running:
                    return
                stream = container.streams.video[self.stream_index]
                pts_list = []

                current_index = 0
                flush_every = 10  # number of frames over which flushing to all points
                for packet in container.demux(stream):
                    for frame in packet.decode():
                        if frame.pts is not None:
                            pts_list.append(frame.pts)
                            if current_index % flush_every == 1:
                                with self._lock:
                                    self.all_pts = pts_list
                                    self._i = current_index
                            current_index += 1
        except Exception as e:
            print("Index thread error:", e)
        finally:
            self._index_ready.set()

    def _need_seek_call(self, current_frame_pts, target_frame_pts):
        with self._lock:
            # return if empty list or empty array or not enough frmae
            if len(self._keypoint_pts) == 0 or self._keypoint_pts[-1] < target_frame_pts:
                return True

        # roll back the stream if video is scrolled backwards
        if current_frame_pts > target_frame_pts:
            return True

        # find the closest keypoint pts before a given frame
        idx = np.searchsorted(self._keypoint_pts, target_frame_pts, side="right")
        closest_keypoint_pts = self._keypoint_pts[max(0, idx - 1)]

        # if target_frame_pts is larger than current (and if code
        # arrives here, it is, see second return statement),
        # then seek forward if there is a future keypoint closest
        # to the target.
        return closest_keypoint_pts > current_frame_pts

    def _get_frame_idx(self, pts: int) -> int:
        """
        Get the frame index from the presentation time stamp.

        Parameters
        ----------
        pts:
            The presentation time stamp of the frame.

        Returns
        -------
        idx:
            The frame index corresponding to the given pts.
        use_time:
            If true, search using presentation time in seconds, otherwise use pts.

        """
        # Wait until enough index is available
        # Estimate pts from index (using filled index if available)
        with self._lock:
            done = self.all_pts[min(self._i, len(self.all_pts) - 1)] > pts
        if done:
            # the pts for this timestamp has been filled
            idx = np.searchsorted(self.all_pts, pts, side="right")
            use_time = False
        else:
            # keep going until at least two frames have been decoded by the thread
            while True:
                with self._lock:
                    if self._i > 1:
                        break
                time.sleep(0.001)
            # use recent history to get the step estimate
            with self._lock:
                # Linear extrapolation from available pts (use last 10 steps for an estimate)
                start, stop = max(self._i - 10, 0), self._i
                avg_step = np.mean(np.diff(self.all_pts[start:stop]))
                idx = int((pts - self.all_pts[0]) / avg_step)
                use_time = True
        return idx, use_time

    def _get_target_frame_pts(self, idx: int) -> Tuple[int, bool]:
        """
        Get the target frame presentation time stamp from frame index.

        Parameters
        ----------
        idx:
            The frame index.

        Returns
        -------
        target_pts:
            The target frame presentation time stamp corresponding to the frame index.
        use_time:
            If true, search using presentation time in seconds, otherwise use pts.

        """
        # Wait until enough index is available
        # Estimate pts from index (using filled index if available)
        with self._lock:
            done = self._i > idx
        if done:
            # the pts for this timestamp has been filled
            target_pts = self.all_pts[idx]
            use_time = False
        else:
            # keep going until at least two frames have been decoded by the thread
            while True:
                with self._lock:
                    if self._i > 1:
                        break
                time.sleep(0.001)
            # use recent history to get the step estimate
            with self._lock:
                # Linear extrapolation from available pts (use last 10 steps for an estimate)
                start, stop = max(self._i - 10, 0), self._i
                avg_step = np.mean(np.diff(self.all_pts[start:stop]))
                target_pts = int(self.all_pts[0] + avg_step * idx)
                use_time = True
        return target_pts, use_time

    def get_key_frame(self, backward) -> av.VideoFrame | NDArray:
        idx = self.last_loaded_idx
        if idx is None:
            # fallback to safe keypoint
            self._pts_keypoint_ready.wait(2.0)
            if len(self._keypoint_pts) > 0:
                idx = self._get_frame_idx(self._keypoint_pts[0])[0]
            else:
                idx = 0  # safe fallback

        # Get the pts of the last loaded index
        target_pts, use_time = self._get_target_frame_pts(idx)

        # Seek the next or previous keyframe based on the direction
        with self._lock:
            delta = max(np.mean(np.diff(self._keypoint_pts[:10])) // 2, 1)
        try:
            self.container.seek(
                int(
                    target_pts + (-delta if backward else delta)
                ),  # if you're on top of a key frame, seek does not move no matter what
                backward=backward,
                any_frame=False,
                stream=self.stream,
            )
        except av.error.PermissionError:
            # seek backward at the end of the file
            self.container.seek(
                int(target_pts),
                backward=True,
                any_frame=False,
                stream=self.stream,
            )

        # Decode the next frame, which should be a keyframe
        frame = next(
            frame
            for packet in self.container.demux(self.stream)
            if packet is not None
            for frame in packet.decode()
        )

        self.current_frame = frame

        # Get the index of the key frame
        self.last_loaded_idx = self._get_frame_idx(frame.pts)[0] - 1

        # Return both
        return (
            self.current_frame.to_ndarray(format="rgb24")[::-1] / 255.0
            if self.return_frame_array
            else self.current_frame,
            self.last_loaded_idx,
        )

    def get(self, ts: float) -> av.VideoFrame | NDArray:
        if not self.__class__._get_from_index:
            idx = ts_to_index(ts, self.time)
        else:
            idx = ts

        if idx == self.last_loaded_idx:
            return (
                self.current_frame.to_ndarray(format="rgb24")[::-1] / 255.0
                if self.return_frame_array
                else self.current_frame
            )

        target_pts, use_time = self._get_target_frame_pts(idx)

        if not hasattr(self.current_frame, "pts") or self._need_seek_call(
            self.current_frame.pts, target_pts
        ):
            self.container.seek(
                int(target_pts), backward=True, any_frame=False, stream=self.stream
            )

        # Decode forward from the keypoint until the frame just before (or equal to) target_pts
        last_idx, preceding_frame = self._decode_and_check_frames(use_time, target_pts, idx)

        if preceding_frame is not None:
            self.last_loaded_idx = idx
            self.current_frame = preceding_frame

        return (
            self.current_frame.to_ndarray(format="rgb24")[::-1] / 255.0
            if self.return_frame_array
            else self.current_frame
        )

    def _frame_iterator(self, fall_back_pts: int | None):
        """
        Safe frame iterator.

        Iterate frames from current stream location. If End-of-File error is
        hit, seek to pts and iterate over frames from there.
        """
        try:
            for packet in self.container.demux(self.stream):
                if packet is None:
                    continue
                for frame in packet.decode():
                    if frame.pts is None:
                        continue
                    yield frame
        except av.error.EOFError as e:
            if fall_back_pts is None:
                raise e
            self.container.seek(
                int(fall_back_pts), backward=True, any_frame=False, stream=self.stream
            )
            yield from self._frame_iterator(None)

    def _decode_and_check_frames(self, use_time: bool, target_pts: int, idx: int):
        """Decode from stream."""
        preceding_frame = None
        last_idx = self.last_loaded_idx
        frame_duration = 1 / float(self.stream.average_rate)
        time_threshold = self.round_fn(idx * frame_duration)

        for frame in self._frame_iterator(target_pts):
            if frame.pts is None:
                continue
            if (not use_time and frame.pts > target_pts) or (
                use_time and frame.time > time_threshold
            ):
                last_idx = idx
                current_frame = preceding_frame or frame
                return last_idx, current_frame
            elif (not use_time and frame.pts == target_pts) or (
                use_time and frame.time == time_threshold
            ):
                last_idx = idx
                current_frame = frame
                return last_idx, current_frame
            preceding_frame = frame
        return last_idx, preceding_frame

    @property
    def shape(self):
        if (
            self._time_provided
        ):  # TODO maybe check what is the actual number of frames decoded and throw a warning
            return len(self.time), self.stream.width, self.stream.height
        has_frames = hasattr(self.stream, "frames") and self.stream.frames > 0
        is_done_unpacking = self._index_ready.is_set()
        if not has_frames and not is_done_unpacking:
            warnings.warn(
                message="Video ``shape``, which corresponds to the number of frames, is being "
                "calculated runtime and will be updated.",
                stacklevel=2,
            )
        return (
            (len(self.time), self.stream.width, self.stream.height)
            if has_frames
            else (len(self.all_pts), self.stream.width, self.stream.height)
        )

    @property
    def index(self):
        if self._time_provided:
            return self.time
        else:
            has_frames = hasattr(self.stream, "frames") and self.stream.frames > 0
            is_done_unpacking = self._index_ready.is_set()
            if not has_frames and not is_done_unpacking:
                warnings.warn(
                    message="Video ``shape``, which corresponds to the number of frames, is being "
                    "calculated runtime and will be updated.",
                    stacklevel=2,
                )
            return self.time

    @property
    def t(self):
        return self.time

    def close(self):
        """Close the video stream."""
        self._running = False
        if self._index_thread.is_alive():
            self._index_thread.join(timeout=1)  # Be conservative, don’t block forever
        if self._keypoint_thread.is_alive():
            self._keypoint_thread.join(timeout=1)
        try:
            self.container.close()
        except Exception:
            print("VideoHandler failed to close the video stream.")
        finally:
            # dropping refs to fully close av.InputContainer
            self.container = None
            self.stream = None

    def _wait_for_index(self, timeout=2.0):
        """Wait up to timeout.

        For debugging purposes, or testing, make sure that the
        threads are completed.
        """
        self._index_ready.wait(timeout)
        self._pts_keypoint_ready.wait(timeout)

    def get_slice(self, start: float, end: float = None):
        # TODO check start and end are sorted
        start = ts_to_index(start, self.time)
        if end:
            end = ts_to_index(end, self.time)
            return slice(start, end)
        else:
            return slice(start, start + 1)

    def _append_frame(self, frames, idx, frame):
        if self.return_frame_array:
            frames[idx] = frame.to_ndarray(format="rgb24")[::-1] / 255.0
        else:
            frames.append(frame)

    def _decode_multiple(
        self,
        target_pts,
        idx_start: int,
        idx_end: int,
        step: int = 1,
    ) -> Tuple[int, List[av.VideoFrame] | NDArray, av.VideoFrame]:
        effective_end = min(idx_end, self.shape[0])
        indices = np.arange(idx_start, effective_end, step)
        num_frames = len(indices)
        time_threshold_all = self.round_fn(indices)

        if self.return_frame_array:
            frames = np.empty(
                (num_frames, self.shape[2], self.shape[1], 3),
                dtype=np.float32,
            )
        else:
            frames = []

        collected = 0

        # initialize current frame
        if self.current_frame is None:
            self.get(0)

        preceding_frame = self.current_frame
        go_to_next_packet = False

        while collected < num_frames:
            if not go_to_next_packet:
                target_pts, use_time = self._get_target_frame_pts(indices[collected])

            # First frame shortcut
            if collected == 0 and hasattr(self.current_frame, "pts"):
                if self.current_frame.pts == target_pts:
                    self._append_frame(frames, collected, self.current_frame)
                    collected = 1
                    continue
                elif self.current_frame.pts > target_pts:
                    self.current_frame = None
                    self.container.seek(
                        int(target_pts),
                        backward=True,
                        any_frame=False,
                        stream=self.stream,
                    )
                    go_to_next_packet = True

            if not go_to_next_packet and self._need_seek_call(preceding_frame.pts, target_pts):
                self.container.seek(
                    int(target_pts),
                    backward=True,
                    any_frame=False,
                    stream=self.stream,
                )

            packet = next(self.container.demux(self.stream))

            try:
                decoded = packet.decode()
                while len(decoded) == 0:
                    decoded = packet.decode()
            except av.error.EOFError:
                # end of the video, rewind
                break

            for frame in decoded:
                if frame.pts is None:
                    continue

                time_threshold = time_threshold_all[collected]
                found_next = (
                    (frame.pts > target_pts) if not use_time else (frame.time > time_threshold)
                )
                found_current = (
                    (frame.pts == target_pts) if not use_time else (frame.time == time_threshold)
                )

                if found_next:
                    self._append_frame(frames, collected, preceding_frame)
                    collected += 1
                    go_to_next_packet = False

                elif found_current:
                    self._append_frame(frames, collected, frame)
                    collected += 1
                    go_to_next_packet = False

                else:
                    go_to_next_packet = True

                preceding_frame = frame

        return indices[-1], frames, frame

    def __getitem__(self, idx: slice | int):
        """
        Get item for video frame.

        Gets one or more frames from a video.

        Parameters
        ----------
        idx:
            The index for slicing.

        Returns
        -------
        frame:
            A video frame.

        """
        if isinstance(idx, slice):
            # Fill in missing slice components
            start = idx.start or 0
            if start >= self.shape[0]:
                if self.return_frame_array:
                    return np.empty((0, self.shape[2], self.shape[1], 3))
                else:
                    return []
            stop = idx.stop if idx.stop is not None else self.shape[0]
            step = idx.step if idx.step is not None else 1

            # convert negative vals
            start = start if start >= 0 else start + self.shape[0]
            start = max(0, min(start, self.shape[0]))
            stop = stop + self.shape[0] if stop < 0 else stop
            stop = max(0, min(stop, self.shape[0]))

            # revert slice if negative step
            revert = step < 0
            step = abs(step)

            if (stop - start) // step > 1:
                target_pts, use_time = self._get_target_frame_pts(start)

                if not hasattr(self.current_frame, "pts") or self._need_seek_call(
                    self.current_frame.pts, target_pts
                ):
                    self.container.seek(
                        int(target_pts), backward=True, any_frame=False, stream=self.stream
                    )

                frame_idx, frames, last_frame = self._decode_multiple(
                    target_pts, start, stop, step=step
                )
                # update current decoded frame
                if len(frames):
                    self.last_loaded_idx = frame_idx
                    self.current_frame = last_frame
                return frames if not revert else frames[::-1]

        # Default case: single index
        with self._set_get_from_index(True):
            # TODO CHeck borders
            idx_start = idx if not hasattr(idx, "start") else idx.start
            idx_start = idx_start if idx_start >= 0 else self.shape[0] + idx_start
            frame = self.get(idx_start)
            if isinstance(idx, slice):
                frame = np.expand_dims(frame, axis=0)

        return frame

    def __len__(self):
        return self.shape[0]

    # context protocol
    # (with VideoHandler(path) as video ensure closing)
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
