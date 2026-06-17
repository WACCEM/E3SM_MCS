#!/bin/bash
#SBATCH -A m1867
#SBATCH -J E-YEAR
#SBATCH --qos=regular
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=128   # 128 workers per node (1 worker per core)
#SBATCH --cpus-per-task=1       # 1 CPU per worker
#SBATCH -C cpu
#SBATCH --time=03:00:00
#SBATCH --exclusive
#SBATCH --mail-user=zhe.feng@pnnl.gov
#SBATCH --mail-type=END
#SBATCH --output=logs/log_E3SM_ctl_YEAR.log

#-------------------------------------------------------------------------------
# On NERSC Perlmutter, a full year of hourly MCS tracking with 1° resolution 
# takes about x hours with 1 nodes 128 workers per node.
#-------------------------------------------------------------------------------

date

module load python
source activate /global/common/software/m1867/python/pyflex26.3

# Run Python
python /global/homes/f/feng045/program/PyFLEXTRKR-dev/runscripts/run_mcs_tbpf_mcsmip.py \
       /global/homes/f/feng045/program/e3sm_polun/tracking/config_mcs_tbpf_E3SM_ctl_YEAR.yml

date
