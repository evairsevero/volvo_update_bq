#!/usr/bin/env bash
# Cria (ou atualiza) o job do Cloud Scheduler que chama a função carga-meta-dashboard a cada 15 minutos.
# Requer cloudscheduler.jobs.create e actAs na conta de serviço. Rodar depois do deploy.sh.
set -euo pipefail

PROJ=volvo-iam
REGIAO=southamerica-east1
FUNCAO=carga-meta-dashboard
JOB=carga-meta-dashboard
SA=${SA:-sa-cloudfunctions@$PROJ.iam.gserviceaccount.com}

URL=$(gcloud functions describe $FUNCAO --project $PROJ --region $REGIAO --gen2 --format "value(serviceConfig.uri)")

ARGS=(--project $PROJ --location $REGIAO --schedule "*/15 * * * *" --time-zone America/Sao_Paulo
      --uri "$URL" --http-method POST --oidc-service-account-email $SA --oidc-token-audience "$URL"
      --attempt-deadline 300s --max-retry-attempts 2 --min-backoff 60s)
if gcloud scheduler jobs describe $JOB --project $PROJ --location $REGIAO >/dev/null 2>&1; then
  gcloud scheduler jobs update http $JOB "${ARGS[@]}"
else
  gcloud scheduler jobs create http $JOB "${ARGS[@]}"
fi

gcloud scheduler jobs run $JOB --project $PROJ --location $REGIAO
echo "Job $JOB criado e disparado uma vez."
