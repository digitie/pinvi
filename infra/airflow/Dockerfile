ARG AIRFLOW_IMAGE_NAME=apache/airflow:3.2.1-python3.12
ARG AIRFLOW_VERSION=3.2.1
FROM ${AIRFLOW_IMAGE_NAME}

COPY infra/airflow/requirements.txt /requirements.txt

RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" -r /requirements.txt
