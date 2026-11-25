FROM python:3.14-slim

WORKDIR /app

# Install dependencies first so Docker layer caching kicks in on code changes
COPY kuberview/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY kuberview/ ./kuberview/

# Don't run as root inside the container
RUN useradd --no-create-home --uid 10001 kuberview
USER 10001

EXPOSE 8000
CMD ["uvicorn", "kuberview.main:app", "--host", "0.0.0.0", "--port", "8000"]
