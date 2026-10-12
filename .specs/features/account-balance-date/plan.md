# Plano: data do saldo salva na conta (`balance_date`)

**Origem:** pedido do dono, depois do PR #2 (B2). **Estado:** plano, nada implementado. Segue o fluxo do `tlc-spec-driven` (Specify, Design, Tasks, Execute) quando aprovado.

## 1. Problema

Hoje a "Data do saldo" não é guardada na conta. Ela existe só como a `date` da transação sintética `source="opening_balance"`, e o piso do B2 (`within_opening_floor`) a lê dessa transação com um subselect correlacionado. Isso causa quatro falhas:

| # | Falha | Onde |
|---|-------|------|
| 1 | Com saldo `0` a transação de saldo inicial é apagada (ou nem criada), então a data escolhida some | `account_service.py:285` (criação), `:406-431` (edição) |
| 2 | Editar só a data, sem mexer no saldo, só funciona se a transação já existir | `account_service.py:428-437` |
| 3 | O modal de edição mostra sempre hoje, não a data gravada, e o usuário não vê o piso vigente | `accounts.tsx:704-712`, `:841` |
| 4 | O piso depende de uma linha que o sync, o usuário ou uma migração podem recriar, e cada leitura de saldo paga um subselect | `_query_filters.py:57-80`, 10 pontos de uso |

**Objetivo:** a data escolhida pelo usuário vira um dado da conta (`accounts.balance_date`), e todos os lugares que somam transações para exibir saldo passam a usá-la como data de corte.

## 2. Decisões de design

| Decisão | Escolha | Motivo |
|---------|---------|--------|
| Onde guardar | Coluna `accounts.balance_date DATE NULL` (fonte da verdade do piso) | Sobrevive a saldo `0`, edição só de data e recriação da transação sintética |
| Relação com a transação de saldo inicial | Ela continua existindo (valor do saldo) e **espelha** `balance_date`; a conta manda | Mantém relatórios, histórico e saldo corrente sem reescrever o modelo |
| `NULL` | Sem piso (comportamento de antes do B2) | Contas antigas sem saldo inicial e contas conectadas |
| Contas conectadas | Ficam com `balance_date = NULL`; o provedor continua sendo a fonte do saldo | O sync já datava a abertura um dia antes da transação mais antiga, então o piso era no-op |
| Nome do campo na API | `balance_date` na leitura e na escrita (já existe na escrita) | Evita um segundo nome para o mesmo conceito |
| Leitura do piso | `Account.balance_date` (join ou coluna já presente), sem subselect em `transactions` | Menos custo por consulta e um único ponto de verdade |

Decisões que preciso de você (propostas entre parênteses):
- **Q1.** Saldo `0` com data escolhida: gravar `balance_date` e **manter** o piso, sem criar transação de saldo inicial? (Sim: "o saldo era 0 em D" é informação válida.)
- **Q2.** Editar saldo ou data de conta que não tinha `balance_date`: o que gravar quando o usuário não mexe na data? (Não mexer: só grava a data quando o usuário a alterar ou ao criar a conta.)
- **Q3.** Conta existente com saldo inicial: o backfill copia a data da transação sintética (a mais recente, igual ao B2 hoje). Confirma?
- **Q4.** Contas conectadas devem poder ter `balance_date` definido pelo usuário? (Não neste release: continuam derivando do provedor.)

## 3. Mudanças por camada

### 3.1 Banco e modelo
- Migration `098`: adiciona `accounts.balance_date` (Date, nullable). Backfill: `UPDATE accounts SET balance_date = (SELECT max(t.date) FROM transactions t WHERE t.account_id = accounts.id AND t.source = 'opening_balance')` para contas manuais. Downgrade remove a coluna.
- `models/account.py`: campo `balance_date: Mapped[Optional[date]]`.
- Os 7 pontos que constroem `Account(...)` (`core/auth.py`, `api/setup.py`, `api/oidc_auth.py`, `connection_service.py` x2, `admin_service.py`, `account_service.py`) não precisam mudar: o padrão é `NULL`. Só o `create_account` grava a data.

### 3.2 Escrita (`account_service.py`)
- `create_account`: sempre grava `account.balance_date = data.balance_date or app_today()` quando a conta é manual; cria a transação de saldo inicial só se o saldo for diferente de `0`, com `date = account.balance_date`.
- `update_account`: se `balance_date` vier no payload, grava na conta e propaga para a transação de saldo inicial existente (e para o `effective_date`). Se `balance` vier, mantém a regra atual (cria, atualiza ou apaga a transação) usando `account.balance_date` como data. Saldo `0` apaga a transação mas **não** a data.
- Esquemas: `AccountRead` passa a expor `balance_date`; `AccountUpdate`/`AccountCreate` já o aceitam.
- Rejeitar `balance_date` no futuro? (Proposta: permitir; o piso só passa a valer quando a data chegar. Confirmar em Q5.)

### 3.3 Leitura do saldo (os "lugares que mostram saldo")
Trocar a implementação de `within_opening_floor(cutoff)` para usar `Account.balance_date` em vez do subselect. A assinatura e a semântica ficam iguais (AD-001): `balance_date IS NULL OR cutoff < balance_date OR Transaction.date >= balance_date`. Isso atualiza de uma vez os 10 pontos já cobertos:

| Ponto | Arquivo:linha |
|-------|---------------|
| Lista de contas e `previous_balance` | `account_service.py:77`, `:101` |
| Resumo da conta (saldo atual e saldo de abertura da janela) | `account_service.py:715`, `:981` |
| Histórico/série diária da conta | `account_service.py:1028` |
| Snapshots de dashboard, metas e relatórios | `dashboard_service.py:1333`, `:1397` |
| Aviso de reset no patrimônio (`_find_balance_resets`) | `report_service.py:319-338`: usar `Account.balance_date` em vez de `max(opening_balance.date)` |

Cada consulta que usa `within_opening_floor` já faz join com `Account` (ou precisa passar a fazer: confirmar nos 6 sites na fase de design). Quem ainda não tiver o join ganha um.

### 3.4 Frontend
- `types/index.ts`: `Account.balance_date: string | null`.
- `accounts.tsx` (`AccountDialog`): o campo "Data do saldo" inicia com `account.balance_date` na edição e com hoje na criação. O envio continua só quando o usuário mexer no saldo ou na data (T7 do PR #2). Mostrar uma dica abaixo do campo: "Transações anteriores a esta data não alteram o saldo."
- Detalhe da conta e lista: onde fizer sentido, exibir "Saldo desde dd/mm" para o usuário entender o piso (a confirmar no design).
- i18n: dica do campo em todos os locales.

### 3.5 Compatibilidade e outros consumidores
- **Transações:** a transação de saldo inicial segue oculta da lista (`include_opening_balance=False`); nenhuma mudança.
- **Import/export e backup:** o backup é `pg_dump`, então a coluna entra sozinha. Restaurar um backup antigo (sem a coluna) em código novo exige a migration `098` (o `alembic upgrade head` do backend já cobre).
- **MCP/agents** (`mcp_server/tools/accounts.py`): passa a poder expor `balance_date` no resumo; opcional.
- **Detalhe da conta (F10):** com a data guardada na conta, o gráfico do detalhe pode aplicar o piso na soma corrente. Isso resolve o resíduo F10 do PR #2; incluir como tarefa opcional.

## 4. Requisitos (rascunho EARS)

1. WHEN o usuário cria uma conta manual com data do saldo D THEN o sistema SHALL gravar `accounts.balance_date = D`.
2. WHEN o usuário cria uma conta com saldo `0` e data D THEN o sistema SHALL gravar `balance_date = D` e SHALL NOT criar transação de saldo inicial.
3. WHEN o usuário altera apenas a data do saldo THEN o sistema SHALL atualizar `balance_date` e a data da transação de saldo inicial, se existir.
4. WHEN o usuário abre o modal de edição THEN o sistema SHALL mostrar `balance_date` da conta.
5. WHILE `balance_date` for `NULL` o sistema SHALL somar todas as transações contáveis (sem piso).
6. WHILE `balance_date` for D o saldo exibido SHALL somar apenas transações com data `>= D` (e a de saldo inicial), em todos os pontos de leitura listados em 3.3.
7. WHEN a data de corte da consulta for anterior a D THEN o sistema SHALL incluir todas as transações até esse corte (séries históricas, como hoje).
8. WHERE a conta é conectada o sistema SHALL ignorar `balance_date` e manter o saldo do provedor.
9. WHEN a migration `098` roda THEN o sistema SHALL preencher `balance_date` das contas manuais com a data mais recente da transação de saldo inicial.

## 5. Tarefas propostas (ordem de execução)

| # | Tarefa | Arquivo principal | Testes |
|---|--------|-------------------|--------|
| 1 | Coluna e modelo `balance_date` | `models/account.py` | build |
| 2 | Migration `098` com backfill e downgrade | `alembic/versions/098_account_balance_date.py` | teste de backfill |
| 3 | Esquemas: `balance_date` na leitura | `schemas/account.py` | build |
| 4 | Criar conta grava a data, inclusive com saldo `0` | `account_service.py` | unit |
| 5 | Editar conta: só data, saldo `0`, propagação à transação sintética | `account_service.py` | unit + API |
| 6 | `within_opening_floor` lê `Account.balance_date`; garantir o join em cada ponto | `_query_filters.py` + 6 sites | unit por ponto (regressão do B2) |
| 7 | `_find_balance_resets` usa `balance_date` | `report_service.py` | unit |
| 8 | Tipos e modal: data inicial da edição, dica | `types/index.ts`, `accounts.tsx` | unit |
| 9 | i18n da dica (15 locales) | `locales/` | paridade |
| 10 | (opcional) Piso na soma corrente do detalhe da conta (F10) | `account-detail.tsx` | unit |
| 11 | Notas de release e `restore.md` | `deploy/public/` | docs |

Fases: **A** (1-3, base de dados), **B** (4-7, comportamento), **C** (8-11, interface e docs).

## 6. Riscos

| Risco | Mitigação |
|-------|-----------|
| Backfill muda o piso de contas existentes | Copia a data que o B2 já usa (a mais recente da transação sintética), então o saldo exibido não muda |
| Divergência entre `balance_date` e a data da transação sintética | A conta manda: toda escrita atualiza as duas no mesmo commit; teste de consistência |
| Ponto de leitura sem join com `accounts` quebra a consulta | Teste por ponto (já existem 10 para o B2) rodando contra o novo filtro |
| Restaurar backup de produção no dev com a branch nova | O script `restore-to-dev.sh` já deixa o backend rodar `alembic upgrade head` (aplica a `098`) |
| Contas conectadas | Sem mudança de comportamento; teste de regressão |

## 7. Fora de escopo

- Permitir `balance_date` em contas conectadas (Q4).
- Mudar o histórico de patrimônio antes da data do saldo (continua como decidido no B2).
- Reescrever a transação sintética de saldo inicial como entidade própria.

## 8. Próximo passo

Responder Q1-Q5. Depois disso, gero o spec, o design e as tarefas no formato do `tlc-spec-driven` em `.specs/features/account-balance-date/` e executo em lotes, com Verifier no final.
