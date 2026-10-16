FROM python:3.12-slim
WORKDIR /app
COPY libs/mimamori-common/ libs/mimamori-common/
RUN pip install --no-cache-dir "./libs/mimamori-common[web,cloud]"
COPY services/conversation-svc/ services/conversation-svc/
RUN pip install --no-cache-dir ./services/conversation-svc
# call-turn.json (constrained decoding) and examples/call-templates.json (approved wording) are read at runtime
COPY schemas/ schemas/
ENV PORT=8080 MIMAMORI_SERVICE=conversation-svc
CMD ["sh", "-c", "uvicorn conversation_svc.main:app --host 0.0.0.0 --port $PORT"]
