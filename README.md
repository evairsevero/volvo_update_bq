# Carga `dados_meta_dashboard` a cada 15 min (Cloud SQL → BigQuery)

```
Cloud Scheduler (*/15 * * * *, America/Sao_Paulo)
   │ POST autenticado (OIDC)
   ▼
Cloud Function gen2 carga-meta-dashboard   (southamerica-east1, Direct VPC egress na rede volvo-iam)
   │ 1. SELECT na view sch_vendadiretaprd.dados_meta_dashboard  (Cloud SQL prd-venda-direta, IP privado)
   │ 2. load job WRITE_TRUNCATE
   ▼
BigQuery volvo-iam.vendas.dados_meta_dashboard
```

- A cada 15 minutos a tabela é **substituída** pela view inteira (troca atômica, idempotente). A coluna extra
  `data_carga` (TIMESTAMP, UTC) indica quando os dados foram carregados.
- Se a view vier vazia, a carga é abortada (HTTP 500) e a tabela mantém os dados anteriores.
- A sessão no banco é somente leitura e com `statement_timeout`.

## Deploy

Dois passos, com `gcloud` logado no `volvo-iam`:

```bash
./deploy.sh       # publica/atualiza a função (pede a senha do ai_poc; outro usuário: DB_USER=fulano ./deploy.sh)
./scheduler.sh    # cria o job (a cada 15 min) e dispara uma vez (exige cloudscheduler.jobs.create)
```

A função roda com a conta `sa-cloudfunctions@volvo-iam` (já tem `cloudsql.editor` e `bigquery.admin`), que também é
a identidade que o Scheduler usa para chamá-la. Outra conta: `SA=... ./deploy.sh` e `SA=... ./scheduler.sh`.

Para trocar a senha, rode `./deploy.sh` de novo. A senha fica visível na configuração da função para quem tem
leitura em Cloud Functions/Cloud Run no projeto.

## Operação

```bash
gcloud scheduler jobs run carga-meta-dashboard --location southamerica-east1 --project volvo-iam   # rodar agora
gcloud functions logs read carga-meta-dashboard --region southamerica-east1 --gen2 --project volvo-iam --limit 20
bq query --use_legacy_sql=false 'SELECT max(data_carga), count(*) FROM `volvo-iam.vendas.dados_meta_dashboard`'
```

## Rodar local (pelo túnel IAP)

```bash
gcloud compute ssh volvo-bastion-iap --tunnel-through-iap --zone=southamerica-east1-b \
  --project=volvo-iam --ssh-flag="-L 3308:localhost:3308"        # outro terminal

python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
DB_HOST=localhost DB_PORT=3308 DB_USER=ai_poc DB_PASSWORD=... .venv/bin/python main.py
```

Com `DB_HOST` definido o script conecta direto (túnel); sem ele, usa o Cloud SQL Connector com
`INSTANCE_CONNECTION_NAME` (IP privado), como na GCP.
