#!/usr/bin/env python
"""
Generate IMERG 1° MCS tracking config YAML files and Slurm job scripts
from templates, with an option to submit the Slurm jobs.

Input data lives in per-year sub-directories under INPUT_DATA_DIR:
    /pscratch/sd/p/plma/mcs/1deg/{YYYY}0101.0000_{YYYY+1}0101.0000/merg_YYYYMMDDHH_10km-pixel.nc

The config template contains a STARTTIME_ENDTIME placeholder in clouddata_path
that is expanded to the per-year subdirectory name ({startdate}_{enddate}).

Usage examples:
    # Write both config + slurm files for default year range (2007–2020)
    python gen_imerg_tracking_scripts.py

    # Write for a custom year range
    python gen_imerg_tracking_scripts.py --start-year 2010 --end-year 2015

    # Write only config files
    python gen_imerg_tracking_scripts.py --no-write_slurm

    # Write files AND submit all jobs
    python gen_imerg_tracking_scripts.py --submit

    # Submit without re-writing files (files must already exist)
    python gen_imerg_tracking_scripts.py --no-write_config --no-write_slurm --submit
"""

import argparse
import glob
import os
import subprocess
import sys

# ──────────────────────────────────────────────────────────────────────────────
# Paths and constants
# ──────────────────────────────────────────────────────────────────────────────

# Base directory; per-year data lives in sub-directories named
# {YYYY}0101.0000_{YYYY+1}0101.0000/
INPUT_DATA_DIR = "/pscratch/sd/p/plma/mcs/1deg"

# This script lives inside the tracking directory — use it as the output directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = SCRIPT_DIR

# Template file paths
CONFIG_TEMPLATE = os.path.join(SCRIPT_DIR, "config_mcs_tbpf_IMERG_ne30_template.yml")
SLURM_TEMPLATE  = os.path.join(SCRIPT_DIR, "slurm_mcs_IMERG_template.sh")

# Output file name patterns (without year or extension, which are added later)
CONFIG_BASENAME = "config_mcs_tbpf_IMERG_"
SLURM_BASENAME  = "slurm_mcs_IMERG_"

# Slurm log directory (must exist before jobs are submitted)
SLURM_LOG_DIR = os.path.join(SCRIPT_DIR, "logs")


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Generate IMERG 1° MCS tracking config YAML and Slurm job scripts "
            "from templates, and optionally submit the jobs."
        )
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=2007,
        help="First year to process (default: 2007)",
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=2020,
        help="Last year to process (default: 2020)",
    )
    parser.add_argument(
        "--write_config",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Write config YAML files (default: True; use --no-write_config to skip)",
    )
    parser.add_argument(
        "--write_slurm",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Write Slurm job scripts (default: True; use --no-write_slurm to skip)",
    )
    parser.add_argument(
        "--submit",
        action="store_true",
        default=False,
        help="Submit Slurm jobs with sbatch after writing the scripts (default: False)",
    )
    return parser.parse_args()


def read_template(path):
    with open(path, "r") as fh:
        return fh.read()


def write_file(path, content):
    with open(path, "w") as fh:
        fh.write(content)
    print(f"  Written : {path}")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    if not (args.write_config or args.write_slurm or args.submit):
        print("Nothing to do — pass --write_config, --write_slurm, or --submit.")
        sys.exit(0)

    if args.start_year > args.end_year:
        print(f"ERROR: --start-year ({args.start_year}) must be <= --end-year ({args.end_year})")
        sys.exit(1)

    # Create the Slurm log directory so the --output path in the script is valid
    os.makedirs(SLURM_LOG_DIR, exist_ok=True)

    # Read templates once
    config_template = read_template(CONFIG_TEMPLATE)
    slurm_template  = read_template(SLURM_TEMPLATE)

    print(f"Processing years {args.start_year}–{args.end_year}\n")
    n_processed = 0

    for year in range(args.start_year, args.end_year + 1):

        # ── Date bounds (year boundaries) ────────────────────────────────────
        startdate = f"{year}0101.0000"
        enddate   = f"{year + 1}0101.0000"

        # ── Count input files for this year ──────────────────────────────────
        # Data lives in: INPUT_DATA_DIR/{startdate}_{enddate}/merg_{year}*.nc
        subfolder = f"{startdate}_{enddate}"
        pattern = os.path.join(INPUT_DATA_DIR, subfolder, f"merg_{year}*.nc")
        files   = sorted(glob.glob(pattern))
        n_files = len(files)
        print(f"{year}: {n_files} file(s) found  [{subfolder}]")

        if n_files == 0:
            print(f"  [ERROR] No input files found for {year}, skipping.\n")
            continue

        # ── Output file paths ────────────────────────────────────────────────
        config_fname = f"{CONFIG_BASENAME}{year}.yml"
        slurm_fname  = f"{SLURM_BASENAME}{year}.sh"
        config_path  = os.path.join(OUTPUT_DIR, config_fname)
        slurm_path   = os.path.join(OUTPUT_DIR, slurm_fname)

        # ── Config substitution ──────────────────────────────────────────────
        # Replace STARTTIME_ENDTIME first (the subfolder placeholder in clouddata_path);
        # it is distinct from STARTDATE/ENDDATE so no substring collision.
        # Then replace STARTDATE / ENDDATE before YEAR to avoid partial matches.
        config_text = (
            config_template
            .replace("STARTTIME_ENDTIME", f"{startdate}_{enddate}")
            .replace("STARTDATE", startdate)
            .replace("ENDDATE",   enddate)
            .replace("YEAR",      str(year))
        )

        # ── Slurm substitution ───────────────────────────────────────────────
        slurm_text = slurm_template.replace("YEAR", str(year))

        # ── Write files ──────────────────────────────────────────────────────
        if args.write_config:
            write_file(config_path, config_text)

        if args.write_slurm:
            write_file(slurm_path, slurm_text)
            os.chmod(slurm_path, 0o755)

        # ── Submit ───────────────────────────────────────────────────────────
        if args.submit:
            if not os.path.exists(slurm_path):
                print(
                    f"  [SKIP submit] {slurm_fname} does not exist — "
                    "run with --write_slurm first"
                )
            else:
                result = subprocess.run(
                    ["sbatch", slurm_path],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    print(f"  Submitted: {result.stdout.strip()}")
                else:
                    print(f"  [ERROR] sbatch failed: {result.stderr.strip()}")

        n_processed += 1

    print(f"\nDone. Processed {n_processed} year(s).")


if __name__ == "__main__":
    main()
