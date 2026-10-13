# Cartão de Crédito

Verão base: `v0.16.3-selfhost.3` ・ Versão alvo: `v0.16.3-selfhost.4`

Propostas de melhorias e novas funcionalidades para o contexto de cartão de crédito.

## Melhorias

- **Melhorar a visualização das faturas:** permitir que o usuário veja de forma clara e detalhada todas as transações associadas a cada fatura do cartão de crédito, incluindo datas, valores e categorias. (funcionalidade já coberta pela visualização de detalhes de contas do tipo cartão de crédito) P

  Proposta: nova página `CONTAS > Cartão de Crédito` baseada na visualização de detalhes de contas de cartão de crédito `/accounts/:accountId` que traga o consolidado das contas de cartão de crédito. Exibir mesma visualização, mas com dados agregados de várias faturas e a possibilidade de mudar a visualização para uma conta específica.

- **Importar faturas:** transações importadas para uma conta do tipo "Cartão de Crédito" devem ser automaticamente vinculadas a faturas no cartão de crédito correspondente. 

  Caso não haja uma fatura correspondente, o sistema deve criar uma nova fatura automaticamente ou permitir o usuário criar uma nova fatura manualmente. 

  Dados da fatura: mês/ano, valor total, conta vinculada, status (paga ou pendente), data de vencimento e data do fechamento. O match de transação -> fatura deve ser feito com base na data da transação em relação ao período da fatura (consultar a data de fechamento da conta do cartão de crédito como base de referência para o período).

- **Impactos no dashboard e relatórios:** transações de cartão de crédito que pertencem a uma fatura devem contabilizar como despesas nos cálculos do dashboard e categoria correspondente, quando tiverem sido pagas. Quando estiverem dentro de uma fatura ainda pendente, exibir como despesa futura (estudar viabilidade dentro do contexto de Despesas Projetadas que existe hoje).

- **Impactos no pagamento de faturas:** dentro do contexto de conta corrente, pode aparecer uma transação que paga uma fatura no cartão de crédito. Nesse caso, uma transação que paga uma fatura deve ser vinculada a essa fatura como tipo de pagamento, seja parcial ou integral, e não deve contabilizar nos cálculos do dashboard e relatórios. 

- **Match de transações de pagamento com faturas de cartão de crédito:** vincular automaticamente, quando possível, pagamentos realizados em conta corrente com faturas de cartão de crédito com base no período da fatura e valor. 

  Adicionar novo botão no menu de ações para vincular a uma fatura de cartão de crédito. Exibir pré-visualização do match automático de pagamento -> fatura. Em alguns casos onde a data de vencimento foge do padrão do cartão, o sistema deve deve sugerir o vínculo da fatura, com base na data de pagamento e valor. 

  Exemplo de transação que paga uma fatura: 

  - Descrição: Pagamento de fatura
  - Valor: 1283,20 BRL
  - Data: 14/09/2026
  - Status: Lançada
  - Tipo: Despesa
  - Categoria: Faturas
  - Conta: Nubank

  No caso acima, existe a conta "Nubank" (Conta Corrente) e a conta "Cartão de Crédito Nubank" (Cartão de Crédito), com fechamento dia 5 e vencimento dia 12. Nesse cenário, existe um porém: a fatura foi paga em no dia correto (dia 14, segunda), porém acima do dia padrão (12), que caiu em um sábado (12/09, sábado). O sistema deve considerar o cálculo do dia de vencimento de uma fatura com base em dias úteis e feriados locais do workspace. (para este momento, considerar apenas Brasil)

- **Sugestão de vínculo na listagem de transações:** pagamentos que são de categoria de fatura, podem ser vinculados a faturas. Nesse caso, exibir no menu de ações de transações, um novo botão para vincular a uma fatura. Abrir modal para seleção de fatura e confirmação.