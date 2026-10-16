FROM python:3.12-slim
WORKDIR /app
COPY libs/mimamori-common/ libs/mimamori-common/
RUN pip install --no-cache-dir "./libs/mimamori-common[cloud]"
COPY jobs/intel-job/ jobs/intel-job/
RUN pip install --no-cache-dir ./jobs/intel-job
COPY schemas/ schemas/
CMD ["python", "-m", "intel_job"]
