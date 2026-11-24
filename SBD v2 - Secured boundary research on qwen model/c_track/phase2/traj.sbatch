#!/bin/bash
#SBATCH --account=torch_pr_173_general
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=03:00:00
#SBATCH --job-name=sbd-traj
#SBATCH --output=/scratch/zl5749/sbd-pilot/c_track/phase2/logs/%x-%j.out
# Usage: sbatch traj.sbatch "Qwen/Qwen2.5-Coder-7B-Instruct" qwen7b 0-39
PORT=$((8000 + SLURM_JOB_ID % 1000)); export SBD_BASE_URL="http://localhost:$PORT/v1"
MODEL="$1"; export SBD_TAG="$2"; export SBD_SEEDS="${3:-0-29}"
source /scratch/zl5749/sbd-env2/bin/activate
export HF_HOME=/scratch/zl5749/hf TMPDIR=/scratch/zl5749/tmp SBD_MODEL="$MODEL" SBD_CC=clang
cd /scratch/zl5749/sbd-pilot/c_track/phase2
python run_sbd2.py --calibrate || { echo "CALIBRATION FAILED - not running trajectories"; exit 1; }
vllm serve "$MODEL" --port $PORT --max-model-len 16384 > logs/vllm-$SBD_TAG.log 2>&1 &
VPID=$!
until curl -s localhost:$PORT/v1/models > /dev/null; do
  kill -0 $VPID 2>/dev/null || { echo "vllm died"; tail -30 logs/vllm-$SBD_TAG.log; exit 1; }
  sleep 10
done
python run_sbd2.py
kill $VPID
python analyze_sbd2.py results/$SBD_TAG
