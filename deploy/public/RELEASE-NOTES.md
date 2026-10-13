# Notas de versão do fork

Mudanças de cada versão publicada a partir do fork, da mais nova para a mais antiga. Para publicar e aplicar uma versão, veja
[RELEASING.md](RELEASING.md) e a seção 4 do [RUNBOOK.md](RUNBOOK.md).

## 0.16.3-selfhost.4

Parte de `0.16.3` do projeto original. Toda fatura de cartão de crédito passa a existir no banco, mesmo em cartões alimentados
por importação ou lançamento manual. O pagamento da fatura feito pela conta corrente é vinculado à fatura e deixa de contar como
despesa, o que acaba com a contagem dupla no painel. Há um novo modo contábil, uma página que reúne todos os cartões e um comando
para reconstruir as faturas.

### Antes de atualizar
- **Esta versão traz duas migrations: `099` (estrutura) e `100` (preenchimento das faturas).** As duas rodam sozinhas no
  `alembic upgrade head` ao subir o backend, sem passo manual. Como as migrations não são revertidas, **faça o backup antes** e,
  para voltar atrás, restaure-o junto com a tag anterior (ver [backup/restore.md](backup/restore.md)).
- A `100` cria uma fatura por mês de referência para cada cartão com **dia de fechamento e dia de vencimento** configurados, e liga
  a ela todas as transações do cartão. Ela não mexe nas faturas que vieram do banco (Pluggy) nem nas transações já ligadas a elas.
  Rodar de novo não cria nada. Em bases grandes o primeiro boot pode demorar um pouco mais.
- **Pagamentos antigos de fatura não são vinculados na atualização.** Depois de subir a versão, abra **Transações** e use o
  botão **"Aplicar match de pagamentos"** (no celular, fica no menu de ações). Revise a prévia e aplique. Só os pares marcados
  são vinculados; nada é gravado antes de você confirmar. Até lá, os pagamentos antigos continuam contando como despesa.
- **Marque a categoria das faturas.** Em **Categorias**, edite a categoria usada para os pagamentos de fatura (por exemplo
  "Faturas") e ative **"Pagamento de fatura"**. As transações dessa categoria deixam de contar como receita ou despesa, mesmo antes
  de serem vinculadas a uma fatura. A atualização não cria nem marca categoria nenhuma.
- **Confira os dias de fechamento e vencimento dos cartões perto do fim do mês.** Combinações que fariam dois fechamentos caírem
  no mesmo mês de referência (por exemplo, fechamento 30 e vencimento 31) passam a ser recusadas com o erro
  `incompatible_cycle_days` ao criar ou editar a conta, e nada é gravado. Um cartão que já esteja assim continua funcionando, mas
  **qualquer edição dele é recusada** até você trocar os dias por uma combinação válida.
- Publique como `0.16.3-selfhost.4` (`./deploy/public/release.sh 0.16.3-selfhost.4 --dry-run` e depois sem `--dry-run`).

### Faturas
- **Uma fatura por cartão e mês de referência.** O mês de referência é o mês do vencimento. O período vai do fechamento anterior
  até a véspera do fechamento: uma compra feita no dia do fechamento entra na fatura seguinte. Dias 29 a 31 são ajustados ao último
  dia do mês. Cartões sem dia de fechamento ou de vencimento não ganham faturas automáticas.
- **Vencimento efetivo.** Quando o vencimento cai em fim de semana ou feriado nacional, o vencimento efetivo é o próximo dia útil.
  Exemplo: fechamento dia 5 e vencimento dia 12, fatura de setembro de 2026: período de 05/08 a 04/09, vencimento 12/09 (sábado),
  vencimento efetivo 14/09.
- **Feriados considerados** (só os nacionais, sem estaduais nem municipais): 01/01, segunda e terça de Carnaval, Sexta-feira Santa,
  21/04, 01/05, Corpus Christi, 07/09, 12/10, 02/11, 15/11, 20/11 (desde 2024) e 25/12. Carnaval, Sexta-feira Santa e Corpus Christi
  são calculados a partir da Páscoa. A lista fica em `backend/app/core/business_days.py`; um feriado nacional novo exige mudar esse
  arquivo e publicar uma versão.
- **Totais e situação.** Cada fatura mostra o total calculado (compras menos estornos), o total declarado (opcional, o valor da
  fatura do banco), a diferença entre os dois, o valor pago, o restante e o valor pago a mais. A situação é **aberta**, **fechada**,
  **parcialmente paga**, **paga** ou **vencida**.
- **Importação, lançamento manual e sincronização ligam as transações à fatura**, criando a fatura quando ela não existe. A resposta
  da API de importação informa quantas transações foram ligadas e quantas faturas foram criadas; a tela ainda não mostra esses
  números.
- **No detalhe do cartão**, o quadro "Fatura" mostra a situação, o vencimento efetivo, os totais e os pagamentos do ciclo na tela.
  Dali é possível criar uma fatura manual, editar o total declarado e, em faturas que não vieram do banco, editar as datas ou excluir
  a fatura (as transações e os pagamentos ficam, só desvinculados). Faturas do banco não aceitam mudar datas nem excluir.
- **Mover uma compra para outra fatura.** No diálogo da transação de cartão, o campo "Fatura" lista as faturas do cartão; a opção
  "Automática (pela data)" volta ao comportamento padrão. Ele substitui a antiga data livre de fatura.

### Pagamentos de fatura
- **Vincular a fatura.** Na lista de transações, selecione um débito de uma conta que não é cartão e use "Vincular a fatura". O
  diálogo mostra primeiro as faturas candidatas (com cartão, mês, vencimento efetivo, total e restante) e depois as outras faturas
  em aberto. Um pagamento paga uma única fatura; várias parcelas podem pagar a mesma fatura.
- **O pagamento vinculado sai das receitas e despesas** no painel, nos relatórios e nos orçamentos, em todos os modos contábeis.
  Se o cartão tiver um crédito de mesmo valor perto da data, os dois viram uma transferência; se não tiver, o diálogo oferece criar
  a contrapartida.
- **Match automático.** Depois de importar, sincronizar ou lançar um débito, o sistema vincula sozinho o pagamento quando há uma
  única fatura com o restante igual ao valor, dentro da janela do fechamento até 5 dias depois do vencimento efetivo. Nos demais
  casos a lista mostra "Possível pagamento de fatura", com ações para confirmar ou dispensar. Uma sugestão dispensada não volta.

### Modo contábil "Na liquidação da fatura"
- **Novo terceiro modo**, além de "Regime de caixa" (continua o padrão) e "Regime de competência". Para ativar, um administrador
  abre **Administração → Contabilidade** e escolhe **"Na liquidação da fatura"**. Vale para o servidor todo.
- Nesse modo, as compras de uma fatura contam como despesa, na categoria de cada compra, **na data do pagamento que quitou a
  fatura**. Enquanto a fatura não estiver paga por completo, as compras aparecem como **despesas previstas** no mês do vencimento
  efetivo (ou no mês atual, se a fatura já venceu). Pagamento parcial não reconhece nada. Desvincular o pagamento que quitou a fatura
  devolve as compras para previstas.
- O painel ganha o valor "Faturas de cartão em aberto" (soma do restante das faturas não pagas). No detalhamento, as compras de
  cartão mostram a data usada na conta como data principal e a linha "Lançada em <data da compra> · <cartão>".
- Os modos "Regime de caixa" e "Regime de competência" continuam com os mesmos totais de antes.

### Página "Cartão de Crédito"
- **Novo item "Cartão de Crédito" em Contas** (também na paleta de comandos), em `/accounts/credit-cards`. A página abre no mês do
  próximo vencimento efetivo em aberto e mostra, para todos os cartões ou para um só (o cartão escolhido fica na URL, em
  `?account=`): total das faturas, pago, restante, próximo vencimento, limite total e disponível total. Cartões que dividem o mesmo
  limite contam esse limite uma vez só (o maior do grupo). Abaixo vêm as faturas do mês, com links para os pagamentos, e as
  compras do mês.

### Ajustes depois da revisão
- **Selo "Pagamento de fatura" em Categorias.** A categoria marcada como pagamento de fatura mostra o selo na lista, como já
  acontece com "Transferência" e "Ignorado".
- **Datas da fatura na lista de transações.** No modo "Na liquidação da fatura", uma compra de cartão ligada a uma fatura mostra a
  data usada na conta como data da linha. Acima dela vem "Paga em" (fatura quitada) ou "Pagar até" (fatura em aberto). Abaixo vem
  "Lançada em <data da compra>". Assim o filtro de outubro não parece mostrar gastos de setembro. Exemplo: "Petz Digital",
  comprada em 05/09/2026 na fatura que vence em 13/10/2026, aparece com "Pagar até 13/10/2026" e "Lançada em 05/09/2026". Vale
  na tabela e no celular; no celular, a compra fica no grupo da data da fatura.
- **Selo "Prevista" na lista.** No mesmo modo, compras de faturas ainda não quitadas mostram o selo "Prevista".
- Nos modos "Regime de caixa" e "Regime de competência", a lista continua como antes.
- **Fatura no diálogo da transação de cartão.** O diálogo mostra, só para leitura, a fatura da compra (cartão e mês), a situação e
  "Quitada em <data>" ou "Não quitada · vence em <vencimento efetivo>". Para mudar a fatura, use o campo "Fatura", como antes.
- **Compras previstas por categoria no painel.** No modo "Na liquidação da fatura", o quadro "Gastos por Categoria" mostra ao lado
  da categoria quantas compras ainda estão previstas, por exemplo "Compras (2 previstas)". Categorias sem compras previstas não
  mostram nada.
- **Limite disponível do cartão corrigido.** O detalhe do cartão mostrava o limite inteiro como disponível. Agora o disponível é o
  limite menos o valor devido, calculado com o saldo inicial e a data do saldo, igual à lista de contas. A conta recém-criada já
  volta com o saldo e o disponível certos.
- **O link do pagamento abre a transação.** Na lista de pagamentos de uma fatura (detalhe do cartão e página "Cartão de
  Crédito"), o link abre **Transações** no mês do pagamento, com a transação de pagamento destacada. Antes, abria a conta
  corrente que pagou.

### Extrato de cartão com sinais invertidos
- Alguns bancos exportam o CSV do cartão com os sinais trocados: a compra vem positiva e o pagamento da fatura vem negativo.
  Não há mudança de código para isso. Na importação, marque **"Inverter valores (trocar entrada/saída)"** e salve o mapeamento
  com a conta do cartão. Nas próximas importações desse arquivo, o mapeamento salvo já aplica a inversão.

### Faturas sempre atualizadas
- Os totais e a situação das faturas passam a ser recalculados também quando:
  - uma importação é desfeita;
  - uma conta é excluída (a fatura que ela pagou deixa de constar como paga);
  - um usuário é excluído e os pagamentos dele quitavam faturas de cartões de outros membros do workspace;
  - regras são aplicadas às transações existentes;
  - uma categoria é excluída e as transações dela vão para outra categoria;
  - uma importação substitui uma transação recorrente prevista;
  - a sincronização remove duplicatas de pagamentos.
- Um teste automático passou a barrar qualquer gravação em massa de transações que não recalcule as faturas. Uma exceção só entra
  com o motivo escrito.

### Backups e operação
- **Comando para reconstruir as faturas**, para corrigir totais que fiquem fora do lugar (por exemplo, depois de editar dados direto
  no banco). Ele religa as transações de todos os cartões às faturas, cria as que faltam e recalcula os totais:

  ```
  ./deploy/public/securo-compose exec backend python -m app.cli rebuild-bills
  ./deploy/public/securo-compose exec backend python -m app.cli rebuild-bills --workspace <id-do-workspace>
  ```

  Ele pode rodar mais de uma vez sem efeito colateral e não vincula pagamentos (para isso, use "Aplicar match de pagamentos").

### Banco de dados
- Migration `099_credit_card_bills_v2`: em `credit_card_bills`, `external_id` passa a aceitar vazio e entram `source`,
  `reference_month`, `period_start`, `period_end`, `close_date`, `effective_due_date`, `declared_total`, `computed_total`,
  `paid_amount` e `settled_on`, com índice único por cartão e mês de referência para faturas que não vieram do banco. As faturas
  existentes viram faturas do banco (`source = 'provider'`) com o total declarado igual ao total do banco. Em `transactions` entram
  `paid_bill_id` e `bill_payment_pair`; em `categories`, `is_bill_payment`; e há a tabela nova `bill_payment_dismissals`
  (sugestões dispensadas). O downgrade remove tudo isso e apaga as faturas automáticas e manuais (as transações ficam, só
  desvinculadas); por isso, para voltar atrás, prefira restaurar o backup.
- Migration `100_credit_card_bills_backfill`: cria as faturas automáticas, liga as transações e calcula os totais. O downgrade não
  faz nada; as faturas automáticas somem com o downgrade da `099`.
- Nenhum valor do painel muda no modo "Regime de caixa" com o upgrade, exceto pelos pagamentos que você vincular ou cuja categoria
  marcar como "Pagamento de fatura".

### Limitações conhecidas
- O calendário de dias úteis cobre só feriados nacionais do Brasil.
- Juros, multa, IOF, rotativo e pagamento mínimo calculado não entram nas faturas.
- As mensagens novas estão traduzidas para português e inglês. Nos outros idiomas elas aparecem em inglês (em português de
  Portugal, no texto do Brasil).

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
