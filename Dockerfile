FROM apache/airflow:2.9.2-python3.10

USER root

# Instalar Java JRE para PySpark, utilitarios de red y descarga
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        default-jre-headless \
        procps \
        wget \
        curl \
        gcc \
        g++ \
        libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Configurar JAVA_HOME
ENV JAVA_HOME=/usr/lib/jvm/default-java
ENV PATH="${JAVA_HOME}/bin:${PATH}"

# Descargar el driver JDBC de PostgreSQL para PySpark
RUN mkdir -p /opt/spark/jars && \
    wget -q https://jdbc.postgresql.org/download/postgresql-42.7.3.jar -O /opt/spark/jars/postgresql-42.7.3.jar && \
    chmod 644 /opt/spark/jars/postgresql-42.7.3.jar

# Configurar permisos para usuario airflow
RUN mkdir -p /opt/airflow/data/raw /opt/airflow/data/lake/sets /opt/airflow/data/lake/cards_prices && \
    chown -R airflow:root /opt/airflow/data /opt/spark

USER airflow

# Instalar librerías de Python requeridas
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

ENV PYTHONPATH="/opt/airflow:/opt/airflow/spark_jobs"
ENV POSTGRES_JDBC_JAR="/opt/spark/jars/postgresql-42.7.3.jar"
