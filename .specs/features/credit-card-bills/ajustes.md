# Ajustes pós-termino das tasks

- Incluir badge de "Pagamento de Fatura" na listagem de categoria, assim como aparecem para "Transferências" e "Ignorado".

- Na listagem de transações, mostrar data da quitação da fatura, e não a data de lançamento na fatura (ou seja, ter a mesma visualização que no detalhamento da categoria no card Gastos por Categoria). Isso está causando confusão visual na tela, pois um filtro de 10/2026 está mostrando gastos de 09/2026 (fatura com fechamento em 05/10/2026).

  Ex: Transferência "Petz Digital" lançada em 05/09/2026 na fatura de 10/2026 com vencimento em 13/10/2026 vai exibir:
    - acima da data um texto "Pagar até" ou "Paga em" (dependendo do status da fatura);
    - a data 13/10/2026 do vencimento ou pagamento da fatura;
    - e abaixo dela, vai exibir a data de lançamento (ex: "Lançada em 05/09/2026") igual no drawer de detalhamento da categoria no dashboard.

- Exibir no cadastro da transação de cartão de crédito, a data em que foi quitada (texto informativo, não editável), assim como a fatura correspondente. 

- Extrato de cartão de crédito possui sinais invertidos para despesas e receitas. Na planilha (.csv), um gasto no cartão vem com sinal positivo, enquanto que um pagamento da fatura recebe sinal negativo. 

- Falta badge "PREVISTA" na listagem de transações de cartão de crédito ainda não pagas.

- No dashboard, exibir ao lado da categoria no cartão "Gastos por Categoria" uma badge com a quantidade de transações PREVISTAS (ex: "COMPRAS (2 PREVISTAS)").

- Limite disponível na página de detalhamento da conta de cartão de crédito não está refletindo os valores exatos da conta considerando o saldo inicial. 

- O pagamento da fatura está exibindo a conta que pagou ao invés da transação de pagamento vinculada (ex: link "Pagamentos 13/10/2026 · Pagamento da fatura" redireciona para a conta corrente Nubank que pagou a fatura, ao invés de mostrar a transferência que foi vinculada como pagamento).
