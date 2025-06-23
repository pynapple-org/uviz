from pathlib import Path

from tqdm import tqdm
from one.api import ONE
from PyQt6.QtWidgets import QApplication
import pynapple as nap
import pynaviz as viz
import numpy as np
from brainbox.io.one import SpikeSortingLoader

app = QApplication([])

# ------------------------------------------------------------------------------------
# Load IBL session
one = ONE()
eid = "ebce500b-c530-47de-8cb1-963c552703ea"

# Videos
ibl_path = Path("/home/wolf/Downloads/ONE/")
videos = {}
for label in ["left", "body", "right"]:
    video_path = (
        ibl_path
        / f"openalyx.internationalbrainlab.org/churchlandlab_ucla/Subjects/MFD_09/2023-10-19/001/raw_video_data/_iblrig_{label}Camera.raw.mp4"
    )
    if not video_path.exists():
        one.load_dataset(eid, "*leftCamera.raw*", collection="raw_video_data")
    times = one.load_object(eid, f"{label}Camera", collection="alf", attribute=["times*"])["times"]
    licks = one.load_object(eid, f"{label}Camera", collection="alf", attribute=["times*"])["times"]
    videos[label] = (times, video_path)

# Events and intervals
timings = one.load_object(eid, "trials", collection="alf")
licks = nap.Ts(one.load_object(eid, "licks", collection="alf")["times"])
reactions = nap.Ts(timings["firstMovement_times"])
trials = nap.IntervalSet(timings["intervals"])

# Spikes
ssl = SpikeSortingLoader(eid=eid, one=one)
spikes, clusters, channels = ssl.load_spike_sorting()
clusters = ssl.merge_clusters(spikes, clusters, channels)
clusters = nap.TsGroup(
    {
        cluster_id: nap.Ts(spikes["times"][spikes["clusters"] == cluster_id])
        for cluster_id in tqdm(
            clusters.pop("cluster_id")[:100], unit="cluster", desc="Loading spikes"
        )
    },
    metadata={metadata_key: metadata_values for metadata_key, metadata_values in clusters.items()},
)
subset = nap.IntervalSet(start=0, end=100)
counts = clusters.count(0.001, ep=subset)

# Modulation
# for label, tref, minmax in [
#    ("licks", licks, (-0.1, 0.1)),
#    ("reactions", licks, (-0.2, 0.4)),
#    ("trials", nap.Ts(trials.start), (-0.2, 0.6)),
# ]:
#    psths = nap.compute_perievent_continuous(
#        timeseries=counts,
#        tref=tref,
#        minmax=minmax,
#    ).mean(axis=1)
#    before = (psths.index >= minmax[0]) & (psths.index < 0.0)
#    after = (psths.index >= 0.0) & (psths.index <= minmax[1])
#    clusters[f"{label}_modulation"] = (
#        psths.values[after].mean(axis=0) - psths.values[before].mean(axis=0)
#    ) / (psths.values[after].mean(axis=0) + psths.values[before].mean(axis=0))
#    clusters[f"{label}_peak"] = np.argmax(
#        psths.values[(psths.index >= minmax[0]) & (psths.index < minmax[1])], axis=0
#    )
# clusters = clusters[
#    ~np.isnan(clusters["licks_modulation"])
#    & ~np.isnan(clusters["trials_modulation"])
#    & ~np.isnan(clusters["reactions_modulation"])
#    & (np.abs(clusters["reactions_modulation"]) > 0.1)
# ]


# ------------------------------------------------------------------------------------
# Visualize

# spikes
raster = viz.TsGroupWidget(clusters)
raster.show()
# intervals
raster.plot.add_interval_sets(trials, colors="white", alpha=0.2)
# videos
videos = [
    viz.base_plot.PlotVideo(video_path=video_path, t=times, show_time=0.1)
    for times, video_path in videos.values()
]
# link
viz.controller_group.ControllerGroup(videos + [raster.plot])

if __name__ == "__main__":
    app.exit(app.exec())
