FROM python:3.12-slim
WORKDIR /app
COPY libs/mimamori-common/ libs/mimamori-common/
RUN pip install --no-cache-dir "./libs/mimamori-common[web,cloud]"
COPY services/scoring/ services/scoring/
RUN pip install --no-cache-dir ./services/scoring
ENV PORT=8080 MIMAMORI_SERVICE=scoring
CMD ["sh", "-c", "uvicorn mimamori_scoring.app:app --host 0.0.0.0 --port $PORT"]
