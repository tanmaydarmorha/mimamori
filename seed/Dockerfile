# One-shot loader: seeds the Firestore emulator (or a real project) with case-db, intel-db and ref-db data.
# Build from the repo root: docker build -f seed/Dockerfile .
FROM python:3.12-slim
WORKDIR /app
COPY libs/mimamori-common/ libs/mimamori-common/
RUN pip install --no-cache-dir "./libs/mimamori-common[cloud]"
COPY schemas/ schemas/
COPY seed/ seed/
CMD ["python", "seed/load.py"]
