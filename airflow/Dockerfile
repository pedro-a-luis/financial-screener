# Custom Airflow Image with DAGs Baked In
# Based on official Apache Airflow image
# Includes all DAG files and utilities from the repository

FROM apache/airflow:3.0.2

# Switch to root to install additional packages if needed
USER root

# Install any additional system packages (if needed)
# RUN apt-get update && apt-get install -y <packages> && rm -rf /var/lib/apt/lists/*

# Switch back to airflow user
USER airflow

# Copy DAG files into the image
COPY --chown=airflow:root airflow/dags/ /opt/airflow/dags/

# Install additional Python packages for DAGs (if needed)
# COPY requirements-airflow.txt /tmp/
# RUN pip install --no-cache-dir -r /tmp/requirements-airflow.txt

# Set working directory
WORKDIR /opt/airflow

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD airflow jobs check --job-type SchedulerJob --hostname "$${HOSTNAME}" || exit 1
