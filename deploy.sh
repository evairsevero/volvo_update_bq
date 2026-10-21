#!/usr/bin/env bash
# Deploy da Cloud Function de carga dados_meta_dashboard (Cloud SQL -> BigQuery) no projeto volvo-iam.
# Pode ser rodado de novo para atualizar o código. O agendamento (a cada 15 min) fica em scheduler.sh.
# Uso: ./deploy.sh            (pede a senha do banco; a senha vai como variável de ambiente da função)
set -euo pipefail

PROJ=volvo-iam
REGIAO=southamerica-east1
REDE=volvo-iam
SUBREDE=volvo-iam-sa
INSTANCIA=volvo-iam:southamerica-east1:prd-venda-direta
DB_NAME=dbvolvovendadireta
DB_USER=${DB_USER:-ai_poc}
DATASET=vendas
TABELA=dados_meta_dashboard

FUNCAO=carga-meta-dashboard
# conta de serviço das functions do projeto: já tem cloudsql.editor e bigquery.admin
SA=${SA:-sa-cloudfunctions@$PROJ.iam.gserviceaccount.com}

# APIs necessárias (já habilitadas no volvo-iam): cloudfunctions, run, cloudbuild, artifactregistry,
# cloudscheduler, sqladmin.

[ -n "${DB_PASSWORD:-}" ] || { read -rsp "Senha do usuário $DB_USER: " DB_PASSWORD; echo; }

echo "== Cloud Function"
# Direct VPC egress na rede do banco (padrão: só o tráfego para IPs privados passa pela VPC).
gcloud functions deploy $FUNCAO --project $PROJ --region $REGIAO --gen2 \
  --runtime python312 --source "$(dirname "$0")" --entry-point carga_meta_dashboard \
  --trigger-http --no-allow-unauthenticated \
  --run-service-account $SA \
  --network $REDE --subnet $SUBREDE \
  --memory 512Mi --timeout 300s --max-instances 1 \
  --set-env-vars "^|^INSTANCE_CONNECTION_NAME=$INSTANCIA|DB_NAME=$DB_NAME|DB_USER=$DB_USER|BQ_TABLE=$PROJ.$DATASET.$TABELA|DB_PASSWORD=$DB_PASSWORD"

# o Scheduler chama a função com um token desta mesma conta
gcloud functions add-invoker-policy-binding $FUNCAO --project $PROJ --region $REGIAO --member serviceAccount:$SA >/dev/null

URL=$(gcloud functions describe $FUNCAO --project $PROJ --region $REGIAO --gen2 --format "value(serviceConfig.uri)")
echo "Função publicada: $URL"
echo "Logs: gcloud functions logs read $FUNCAO --project $PROJ --region $REGIAO --gen2 --limit 20"
