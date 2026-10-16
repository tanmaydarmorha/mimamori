# Simulation job (Cloud Run Job, synthetic-only environment). Build from the repo root:
#   docker build -f jobs/sim-job/Dockerfile .
# Copies schemas/ (question banks, playbooks) and seed/ (base synthetic bank for `sim-job seed`).
FROM python:3.12-slim
WORKDIR /app
COPY libs/mimamori-common/ libs/mimamori-common/
RUN pip install --no-cache-dir "./libs/mimamori-common[cloud]"
COPY schemas/ schemas/
COPY seed/ seed/
COPY jobs/sim-job/ jobs/sim-job/
RUN pip install --no-cache-dir ./jobs/sim-job
ENV MIMAMORI_SERVICE=sim-job
# Exits 0 when the report is written; the report goes to the job log (--out -).
CMD ["python", "-m", "sim_job", "run", "--out", "-"]
