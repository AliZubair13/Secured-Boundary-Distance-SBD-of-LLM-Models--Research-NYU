#!/bin/bash
#SBATCH --account=torch_pr_173_general
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=03:00:00
#SBATCH --job-name=sbd-p1
#SBATCH --output=/scratch/zl5749/sbd-pilot/c_track/phase1/logs/%x-%j.out
# Usage: sbatch phase1.sbatch "Qwen/Qwen2.5-Coder-7B-Instruct" tag [N] [LIMIT]
MODEL="$1"; TAG="$2"; export SBD_N="${3:-10}"; export SBD_LIMIT="${4:-0}"
source /scratch/zl5749/sbd-env2/bin/activate
export HF_HOME=/scratch/zl5749/hf TMPDIR=/scratch/zl5749/tmp SBD_MODEL="$MODEL" SBD_CC=clang
cd /scratch/zl5749/sbd-pilot/c_track/phase1
vllm serve "$MODEL" --port 8000 --max-model-len 8192 > logs/vllm-$TAG.log 2>&1 &
VPID=$!
until curl -s localhost:8000/v1/models > /dev/null; do
  kill -0 $VPID 2>/dev/null || { echo "vllm died"; tail -30 logs/vllm-$TAG.log; exit 1; }
  sleep 10
done
python phase1_generate.py data/gen-$TAG.jsonl
kill $VPID
python phase1_judge.py data/gen-$TAG.jsonl data/judged-$TAG.jsonl
python phase1_aggregate.py data/judged-$TAG.jsonl
