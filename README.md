# E3SM ne30 (1°) MCS Tracking & Analysis

This repository contains scripts for tracking Mesoscale Convective Systems (MCS) in the
**E3SM ne30 (~1° / 100 km) `ctl.fr` simulation** and the matching **IMERG 1° observational
dataset**, following the MCSMIP Tb+precipitation protocol
[(Feng et al. 2025 JGR)](<https://doi.org/10.1029/2024JD042204>). 
This is the coarse-resolution (1°) companion to the higher-resolution workflow in `scream/`.

---

## E3SM ne30 MCS tracking workflow

Two datasets are tracked:

| Label | Resolution | Input data directory |
|-------|-----------|----------------------|
| `E3SM ctl.fr` | ~100 km (ne30) | `/pscratch/sd/p/plma/e3sm_scratch/egu2025/ctl.fr/mcs/` |
| `IMERG 1°` | ~100 km (1°×1°) | `/pscratch/sd/p/plma/mcs/1deg/` (per-year sub-directories) |

**Key difference from the SCREAM workflow:** tracking here uses a single Perlmutter CPU
node with a Dask **local cluster** (`run_parallel: 1`, `nprocesses: 128`) rather than
Dask-MPI across multiple nodes. The driver command therefore takes only the config YAML
(no scheduler-file argument).

**Common environment (all tracking jobs):**
- NERSC Perlmutter CPU, account `m1867`, QOS `regular`, `--exclusive`.
- 1 node × 128 processes (Dask local cluster, 1 thread/worker), `run_parallel: 1`.
- Activate: `module load python && source activate /global/common/software/m1867/python/pyflex26.3`
- Driver: `PyFLEXTRKR-dev/runscripts/run_mcs_tbpf_mcsmip.py <config.yml>`
- Pipeline steps (`run_*` flags in config): `idfeature` → `tracksingle` → `gettracks` →
  `trackstats` → `identifymcs` → `matchpf` → `robustmcs` → `mapfeature` → `speed`

All generator scripts below live in `tracking/` unless noted otherwise.

---

### Step 1a — Generate per-year tracking config and Slurm scripts

Two generator scripts produce one config YAML and one Slurm shell script per year by
substituting `STARTDATE`, `ENDDATE`, and `YEAR` placeholders in template files. The IMERG
generator additionally substitutes a `STARTTIME_ENDTIME` placeholder in `clouddata_path`
with the per-year sub-directory name (`{YYYY}0101.0000_{YYYY+1}0101.0000`).

**E3SM ctl.fr** (`tracking/gen_e3sm_tracking_scripts.py`):

```bash
cd tracking/

# Write config YAMLs + Slurm scripts for all years (default: 2001–2020)
python gen_e3sm_tracking_scripts.py

# Custom year range
python gen_e3sm_tracking_scripts.py --start-year 2005 --end-year 2010

# Write files AND submit immediately
python gen_e3sm_tracking_scripts.py --submit

# Submit previously written scripts without regenerating them
python gen_e3sm_tracking_scripts.py --no-write_config --no-write_slurm --submit
```

**OBS: IMERG 1°** (`tracking/gen_imerg_tracking_scripts.py`):

```bash
# Default range: 2007–2020
python gen_imerg_tracking_scripts.py

# Custom range + submit
python gen_imerg_tracking_scripts.py --start-year 2010 --end-year 2015 --submit
```

**Template files** (active pair is set by constants at the top of each generator script):

| Dataset | Config template | Slurm template |
|---------|----------------|----------------|
| E3SM ctl.fr | `config_mcs_tbpf_E3SM_ne30_template.yml` | `slurm_mcs_E3SM_ctl_template.sh` |
| IMERG 1° | `config_mcs_tbpf_IMERG_ne30_template.yml` | `slurm_mcs_IMERG_template.sh` |

Key per-dataset settings in the generated config YAMLs:

| Setting | E3SM ctl.fr | IMERG 1° |
|---------|------------|----------|
| `clouddata_path` | `/pscratch/sd/p/plma/e3sm_scratch/egu2025/ctl.fr/mcs/` | `/pscratch/sd/p/plma/mcs/1deg/{year}0101.0000_{year+1}0101.0000/` |
| `root_path` | `/pscratch/sd/f/feng045/E3SM_polun/E3SM_CTL/{year}/` | `/pscratch/sd/f/feng045/E3SM_polun/OBS/{year}/` |
| `databasename` | `ctl.fr.eam.h3.` | `merg_` |
| `olr2tb` | `True` (OLR→Tb via `FLNT`) | `False` (Tb directly via `Tb`) |
| `pcp_varname` | `PRECT` (+ `pcp_convert_factor: 3600000.0`) | `precipitation` |
| `time_format` | `yyyy-mo-dd` (daily files) | `yyyymoddhh` (hourly files) |
| `idclouds_minute` | — | `30` |

Slurm log files are written to `tracking/logs/` (created automatically).

---

### Step 1b — Tracking performance and Slurm sizing

> **Preliminary — will be updated as more testing is completed.**

Initial estimate based on early testing with 1 node / 128 Dask local-cluster workers:

| Dataset | Estimated wallclock | `--time` in template |
|---------|--------------------|--------------------|
| E3SM ctl.fr | < 2 h / simulation-year | `02:00:00` |
| IMERG 1° | ≥ 2 h / year (TBD) | `03:00:00` |

Note that IMERG has ~8,760 hourly input files per year versus ~365 daily E3SM files. The
`idfeature` step — which processes each file individually and dominates overall runtime —
is therefore expected to be considerably longer for IMERG. Estimates will be refined after
profiling the full pipeline on both datasets.

---

### Step 2 — Monthly MCS precipitation maps (NERSC TaskFarmer)

**Scripts:** `tracking/gen_e3sm_mcs_monthly_stats_taskfarmer.py` (E3SM) /
`tracking/gen_imerg_mcs_monthly_stats_taskfarmer.py` (OBS)

**What it does:** Generates a TaskFarmer tasklist and Slurm submission script. Each task
calls wrapper `scripts/run_mcs_monthly_rainmap_latlon.sh <config.yml> <year> <month>`,
which runs `PyFLEXTRKR-dev/Analysis/calc_tbpf_mcs_monthly_rainmap.py`. For each calendar
month it reads the pixel-tracking files (`mcstrack_*.nc`) and the MCS track statistics,
and produces a monthly MCS precipitation map file.

**Input:** Per-year config YAMLs (from Step 1a) + pixel-tracking NetCDF files
(`<root_path>/mcstracking/mcstrack_YYYYMM*.nc`)

**Output:** Monthly `mcs_rainmap_YYYYMM*.nc` files under `<root_path>/monthly/`

**Peak memory:** ~2 GB per task. Default `THREADS=48` (concurrent tasks/node) is 
conservative — a 512 GB Perlmutter node can safely run far more. 
Raise `--threads` to 64-128 for faster throughput.

```bash
cd tracking/

# Generate tasklist + Slurm script (E3SM, default 2001-01 to 2020-12)
python gen_e3sm_mcs_monthly_stats_taskfarmer.py

# Custom date range, more threads, more nodes
python gen_e3sm_mcs_monthly_stats_taskfarmer.py \
    --start-date 2005-01 --end-date 2010-12 \
    --threads 48 --nodes 2

# Submit (must load taskfarmer module first)
module load taskfarmer
sbatch slurm.submit_mcs_monthly_rainmap_E3SM_ctl.sh

# Same workflow for OBS IMERG (default 2007-01 to 2020-12)
python gen_imerg_mcs_monthly_stats_taskfarmer.py
module load taskfarmer
sbatch slurm.submit_mcs_monthly_rainmap_IMERG.sh
```

---

### Step 3 — Visualization: MCS tracking animations

**Scripts:** `scripts/make_mcs_animation_e3sm.py` (driver) +
`scripts/plot_subset_tbpf_mcs_tracks_demo.py` (plotting worker)

**What it does:**
1. Calls the plotting worker to render a per-timestep PNG for each pixel-level tracking
   file in the requested date range. The worker produces a 2-panel figure: **top panel**
   = IR brightness temperature with MCS mask perimeters and track paths overlaid;
   **bottom panel** = precipitation with tracked MCS filled masks.
2. Stitches all PNGs into an `.mp4` animation using FFmpeg.

Both steps can be toggled independently with `run_plotting` and `run_ffmpeg` booleans at
the top of `make_mcs_animation_e3sm.py`.

**Configuration:** Edit the parameter block at the top of
`scripts/make_mcs_animation_e3sm.py` before running:

```python
# Date range to animate
start_date = "2001-01-01T00"
end_date   = "2001-12-31T23"

# Per-year tracking config YAML (from Step 1a)
config_file = "/global/homes/f/feng045/program/e3sm_polun/tracking/config_mcs_tbpf_E3SM_ctl_2001.yml"

# Map domain extent: [lonmin, lonmax, latmin, latmax]
lon_min, lon_max, lat_min, lat_max = 0.0, 359.9, -60.0, 60.0

# Layout: "1panel" (Tb+Pcp overlaid) or "2panel" (top+bottom panels)
plot_type = "2panel"

# Parallelism: number of Dask workers for PNG generation
n_workers = 128

# Toggle steps
run_plotting = True
run_ffmpeg   = True
```

**Output directories:**
- PNGs: `/pscratch/sd/f/feng045/E3SM_polun/E3SM_CTL/quicklooks_{plot_type}_{data_type}/{start_year}/`
- Animation (`.mp4`): `/pscratch/sd/f/feng045/E3SM_polun/E3SM_CTL/animations_{plot_type}_{data_type}/`

**Running:**

```bash
cd scripts/
python make_mcs_animation_e3sm.py
```

For the full CLI of the plotting worker (figure size, map features, pixel-path directory,
etc.):

```bash
python plot_subset_tbpf_mcs_tracks_demo.py --help
```

---

## Legacy files

The following files are an earlier hand-built monthly-rainmap TaskFarmer example, kept for
reference but superseded by the `tracking/gen_*_mcs_monthly_stats_taskfarmer.py` generators
described in Step 2 above:

- `slurm.mcs_monthly_rainmap_taskfarmer.sh` — manual TaskFarmer Slurm script
- `tasklist_mcs_monthly_e3sm100km.txt` — hand-written task list
- `tracking/config_model100km_mcs_tbpf.yml` — standalone config not tied to the
  per-year generation workflow

These should not be used for new runs.
