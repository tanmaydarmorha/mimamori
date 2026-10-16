# Build from the repo root: docker build -f services/case-svc/Dockerfile .
FROM python:3.12-slim
WORKDIR /app
COPY libs/mimamori-common/ libs/mimamori-common/
RUN pip install --no-cache-dir "./libs/mimamori-common[web,cloud]"
COPY services/case-svc/ services/case-svc/
RUN pip install --no-cache-dir ./services/case-svc
# schemas/ are loaded at runtime (constrained decoding, validation); seed/ fills the in-memory stores in local mode
COPY schemas/ schemas/
COPY seed/ seed/
ENV PORT=8080 \
    MIMAMORI_SERVICE=case-svc
CMD ["sh", "-c", "uvicorn --factory case_svc.app:create_case_app --host 0.0.0.0 --port $PORT"]
