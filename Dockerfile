FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
WORKDIR /app
COPY pyproject.toml requirements.lock alembic.ini ./
COPY src ./src
RUN pip install --no-cache-dir -c requirements.lock . && useradd --create-home appuser
USER appuser
EXPOSE 8000
CMD ["python", "-m", "velocista.infrastructure.startup"]
