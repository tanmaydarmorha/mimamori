FROM python:3.12-slim
WORKDIR /app
COPY libs/mimamori-common/ libs/mimamori-common/
RUN pip install --no-cache-dir "./libs/mimamori-common[cloud]"
COPY jobs/watchlist-loader/ jobs/watchlist-loader/
RUN pip install --no-cache-dir ./jobs/watchlist-loader
ENV MIMAMORI_SERVICE=watchlist-loader
CMD ["python", "-m", "watchlist_loader"]
