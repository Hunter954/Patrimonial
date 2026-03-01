# Sistema Patrimonial (MVP) — Flask

Visual inspirado no print (laranja + cards + gráficos).

## Fluxo do Leitor
- Você escaneia o código (leitor USB = teclado)
- Se o item existir → abre direto na tela de edição
- Se não existir → abre a tela de cadastro já com o código preenchido

## Features do MVP
- Dashboard com KPIs + gráfico por centro de custo + donut de status
- Cadastro/edição de patrimônio
- Geração de etiqueta (barcode Code128) em PNG
- Inventário (filtro + export CSV)
- Relatórios básicos

## Rodar local
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

## Subir no Railway
- Conecta o repositório do GitHub no Railway e deploya.
- Já tem `Procfile`: `web: gunicorn wsgi:app`
- SQLite funciona para teste; para produção use Postgres e defina `DATABASE_URL`.

## Seed
Na primeira inicialização ele cria alguns itens para o dashboard já aparecer preenchido.
