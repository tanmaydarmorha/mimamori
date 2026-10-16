FROM python:3.12-slim
WORKDIR /app
COPY libs/mimamori-common/ libs/mimamori-common/
RUN pip install --no-cache-dir "./libs/mimamori-common[web]"
COPY services/core-bank-mock/ services/core-bank-mock/
RUN pip install --no-cache-dir ./services/core-bank-mock
COPY seed/ seed/
ENV PORT=8080 MIMAMORI_SERVICE=core-bank-mock
CMD ["sh", "-c", "uvicorn core_bank_mock.main:app --host 0.0.0.0 --port $PORT"]
