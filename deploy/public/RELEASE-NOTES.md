# Notas de versão do fork

Mudanças de cada versão publicada a partir do fork, da mais nova para a mais antiga. Para publicar e aplicar uma versão, veja
[RELEASING.md](RELEASING.md) e a seção 4 do [RUNBOOK.md](RUNBOOK.md).

## 0.16.3-selfhost.3

Parte de `0.16.3` do projeto original. Corrige dois problemas de contas, acrescenta quatro recursos que tiravam trabalho manual, melhora a barra de ações da lista de transações e muda a forma como os backups são organizados no R2.

### Antes de atualizar
- **Esta versão traz uma migration nova (`097`, tabela `import_mappings`).** O backend roda `alembic upgrade head` sozinho ao subir
  (`docker-compose.prod.yml`), então não há passo manual. Como as migrations não são revertidas, **faça o backup antes** e, para
  voltar atrás, restaure-o junto com a tag anterior (ver [backup/restore.md](backup/restore.md)). A migration só **cria** uma
  tabela nova; nenhum dado existente é alterado.
- **Também há a migration `098` (coluna `accounts.balance_date`).** Ela roda sozinha ao subir o container, no mesmo
  `alembic upgrade head`, e vale o mesmo aviso: faça o backup antes. Ela adiciona a coluna e preenche a data das contas manuais
  com a data do saldo inicial que cada conta já tem, então **nenhum saldo muda depois da atualização**. Contas ligadas a banco e
  contas sem saldo inicial ficam com a data vazia, como antes. Voltar atrás exige restaurar o backup.
- **Os backups no R2 passam a ficar em uma pasta por backup, na raiz do bucket.** Em vez de arquivos soltos em `securo/`, cada backup vai para
  `securo-backup-AAAA-MM-DD/` (banco, anexos e `.sha256`). O prefixo `securo` deixa de existir (o `R2_PREFIX` do `r2.env` é ignorado). Backups do mesmo dia dividem a pasta. O job agendado usa a
  **cópia** do script em `~/.config/securo-backup/`, então, depois de publicar, atualize-a:
  `cp deploy/public/backup/offsite.sh ~/.config/securo-backup/offsite.sh && chmod 755 ~/.config/securo-backup/offsite.sh`.
  Os arquivos antigos continuam soltos em `securo/` e seguem a mesma retenção (90 dias); nada é movido.
- Publique como `0.16.3-selfhost.3` (`./deploy/public/release.sh 0.16.3-selfhost.3 --dry-run` e depois sem `--dry-run`).

### Correções
- **Diálogo de nova conta abre limpo.** Ao reabrir "Adicionar conta" depois de salvar ou de fechar sem salvar, os campos voltam
  aos valores padrão (nome vazio, tipo conta corrente, saldo 0, moeda do usuário, data de hoje). Antes, ele reaparecia com os
  dados da conta anterior.
- **O saldo inicial passa a ser um piso para o saldo da conta.** O saldo de uma conta é o valor do saldo inicial (a transação
  de origem `opening_balance`) mais as transações **datadas no dia do saldo inicial ou depois**. Transações anteriores a essa data
  continuam aparecendo na lista, mas **não alteram mais o saldo**. Vale para todos os tipos de conta, inclusive cartão de crédito,
  e para a lista de contas, o detalhe, o histórico de saldo e os números do painel, das metas e dos relatórios.

  Exemplo, com saldo inicial de 1000 em 10/10:

  | Transação | Saldo da conta |
  |---|---|
  | despesa de 200 em 05/10 (antes do saldo inicial) | 1000 (não conta) |
  | despesa de 200 em 15/10 | 800 |
  | receita de 200 em 15/10 | 1200 |

  Uma transação datada exatamente em 10/10 conta. Se você editar a data ou o valor do saldo inicial, o saldo é recalculado na
  leitura seguinte, sem migração de dados. Contas sem saldo inicial continuam somando todas as transações, e contas ligadas a
  banco mantêm o mesmo saldo de antes.
- **Aviso no patrimônio líquido.** O gráfico de patrimônio **não** aplica o piso à série histórica: antes da data do saldo
  inicial ele ainda inclui as transações antigas. Por isso, atualizar o saldo de uma conta manualmente pode causar um salto no
  gráfico nessa data. Quando isso acontece, o relatório mostra uma nota dizendo que o saldo da conta foi atualizado manualmente
  naquela data e que a variação reflete essa atualização.
- **A data do saldo agora fica salva na conta.** Antes, a "Data do saldo" escolhida ao criar ou editar uma conta só existia como a
  data da transação de saldo inicial, e se perdia quando o saldo era 0. Agora ela é gravada na própria conta (`balance_date`), o
  diálogo de edição mostra a data salva (ou a de hoje, quando a conta não tem uma) e o piso do saldo passa a ler essa data. A
  transação de saldo inicial continua existindo e acompanha a data e o valor da conta. Consequências:
  - Uma conta com saldo 0 e uma data escolhida guarda a data e aplica o piso, sem criar a transação de saldo inicial.
  - Alterar só a data atualiza a conta e a transação de saldo inicial; editar só o nome não mexe no saldo nem na data.
  - O aviso do patrimônio líquido passa a usar essa data, mesmo quando a conta não tem transação de saldo inicial.
  - O diálogo mostra uma dica sob o campo: "Transações anteriores a esta data não alteram o saldo."
  - Contas ligadas a banco não têm data de saldo própria; o saldo continua vindo do banco.

### Recursos novos
- **Mapeamentos de importação CSV salvos.** Na tela de importação, depois de mapear as colunas você pode salvar o mapeamento com
  um nome e a conta de destino. Ao importar de novo um arquivo com **o mesmo conjunto de colunas** (ordem e espaços nas pontas não
  importam, maiúsculas e minúsculas importam), o mapeamento é aplicado sozinho. Se mais de um combinar, vale o usado mais
  recentemente e os outros ficam selecionáveis. Os mapeamentos são **por usuário** (não por workspace) e os nomes são únicos
  ignorando maiúsculas e minúsculas. Não se aplica a OFX, QIF e CAMT.
- **Ignorar várias transações de uma vez.** Na barra de seleção da lista de transações, "Ignorar" e "Parar de ignorar" definem
  o estado de todas as selecionadas (sem inverter seleções mistas). Até **100** por vez; acima disso os botões ficam desabilitados
  com uma dica. Em uma transferência, só as linhas selecionadas mudam, sem afetar a outra perna.
- **Aplicar a regra de transferência agora, com prévia.** Em Regras, no cartão de transferências, o botão "Aplicar agora" mostra
  os pares que a regra do workspace ligaria entre as transações ainda sem par, **sem gravar nada**. Você desmarca o que não quer
  e confirma; só os pares marcados são ligados, e o aviso informa quantos foram ligados e quantos foram pulados (por exemplo,
  porque uma das pernas foi ligada ou apagada depois da prévia). Só entram pares em que as duas pontas concordam; os casos
  incertos continuam na fila de sugestões, e esta ação não cria sugestões. Exige permissão de escrita.
- **Marcar várias transações como transferência.** Na barra de seleção, "Marcar como transferência" pareia as transações
  selecionadas **entre si**, usando a janela de datas e a tolerância de valor da regra de transferência. A prévia lista os pares
  e separa o que ficou sem contrapartida, o que tem mais de uma contrapartida possível (não é pareado automaticamente) e o que já
  pertence a uma transferência (não é alterado). Até **100** transações por vez; a confirmação revalida cada par antes de ligar.
  Exige permissão de escrita.

### Interface
- **Barra de ações da seleção em ícones com dica.** Na lista de transações, as ações em lote "Adicionar ao grupo", "Vincular como
  transferência", "Marcar como transferência", "Criar regra", "Ignorar" e "Parar de ignorar" viraram botões só com ícone e uma dica
  (tooltip) com o nome. A dica também aparece nos botões desabilitados e explica o motivo (por exemplo, o limite de 100 transações
  ou um par inválido para vincular).
- **A barra não se mexe mais ao abrir um diálogo.** Antes, abrir "Adicionar ao grupo" ou "Vincular transferência" fazia a barra
  deslizar para a direita (a barra de rolagem some e a barra de ações, de largura total, se alargava). Agora ela permanece no lugar.
- **Diálogos de transferência cabem na tela.** "Aplicar a regra de transferência agora" e "Marcar como transferências" extrapolavam
  a largura (a tabela de pares e o texto da lista "sem contrapartida" saíam do diálogo). Eles passaram a usar a largura que o
  conteúdo precisa, e descrições longas são truncadas com a descrição completa na dica.

### Backups e operação
- **Backups no R2 em uma pasta por dia**, na raiz do bucket (`securo-backup-AAAA-MM-DD/`); veja "Antes de atualizar" para o passo de
  atualizar a cópia do script usada pelo agendamento. A retenção de 90 dias continua valendo para as pastas novas e para os
  arquivos antigos soltos em `securo/`, e nenhum outro objeto do bucket é tocado.
- **Script para restaurar um backup de produção no banco de desenvolvimento**
  ([`backup/restore-to-dev.sh`](backup/restore-to-dev.sh)), para testar mudanças contra dados reais antes de publicar. Ele só atua
  no projeto de dev (recusa qualquer coisa de `securo-prod`), não grava o dump em claro no disco, confere o `.sha256`, deixa o backend
  aplicar as migrations novas e mantém o Celery parado para o dev não sincronizar contas bancárias reais. Use `--dry-run` primeiro;
  detalhes em [backup/restore.md](backup/restore.md), seção 6. Não afeta a produção.

### Banco de dados
- Migration `097_import_mappings`: cria `import_mappings` (por usuário; ao apagar o usuário os mapeamentos vão junto; ao apagar
  a conta de destino, o mapeamento fica sem conta).
- Migration `098_account_balance_date`: adiciona `accounts.balance_date` (data, pode ser vazia) e a preenche, nas contas manuais, com
  a data mais recente da transação de saldo inicial; o downgrade apenas remove a coluna.
- Nenhuma outra tabela muda, e nenhum saldo exibido muda com o upgrade.

### Limitações conhecidas
- No detalhe da conta, o saldo corrente do gráfico soma todas as linhas da janela; se a janela cruzar a data do saldo inicial, o
  último ponto pode diferir do saldo atual da conta (que segue a regra do piso).
- Criar uma conta com saldo 0 e **sem** escolher a data não cria piso (a data fica vazia): transações antigas importadas depois
  continuam entrando no saldo. O piso só existe quando você escolhe uma data ou informa um saldo diferente de 0.
- As traduções das novas mensagens nos idiomas além do português do Brasil foram geradas automaticamente e não foram revisadas por
  falantes nativos.
