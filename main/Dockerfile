FROM python:3.9

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    docker.io

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "project.asgi:application"]