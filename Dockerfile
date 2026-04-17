FROM python:3.11-slim

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir pyyaml

EXPOSE 4040 8080

# Start both telnet and web servers
CMD ["sh", "-c", "python3 -m plato --web & python3 -m plato"]
