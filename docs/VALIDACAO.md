# Validação da entrega — Radar Local 1.0

Entrega preparada em 08/10/2026, fuso America/Sao_Paulo.

## Implementado

- Aplicativo local Python + SQLite + painel HTML/CSS/JavaScript em português.
- Campanhas por nicho, localidade, termos e pontos opcionais.
- Demonstração com até dez empresas explicitamente fictícias.
- Coleta de Maps por conector DataForSEO, filtro de anúncios/região e priorização além dos primeiros resultados.
- Candidato Instagram por busca orgânica e confirmação manual.
- Classificação de aderência ao nicho com conector HTTP Jev versionado.
- Pontuação explicável, mediana de posições observadas e completude.
- Importação JSON, exportação CSV filtrada, notas, etapas, não contatar e exclusão.
- Persistência, backup SQLite, limites de chamadas, cancelamento e interrupção após reinício.
- Ferramentas WebMCP opcionais para ler a seleção e abrir o formulário sem iniciar consultas.

## Verificado offline

Ambiente: Python 3.12 e Node 24. A aplicação tem requisito mínimo Python 3.11.

Comandos:

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q app.py radar tests
node --check web/app.js
```

Resultado da suíte: **25 testes aprovados**. Foram exercitados:

1. Valores ausentes, visibilidade desconhecida e mediana somente de posições observadas.
2. Baixa confiança Jev e classificação fora do nicho.
3. URLs válidas de perfil Instagram e rejeição de URLs maliciosas ou de publicações.
4. Validação de tamanho, quantidade e coordenadas.
5. Separação de filiais e de dados fictícios.
6. Exclusão de anúncios e uso de posição orgânica.
7. Importação validada com números ausentes.
8. Deduplicação entre consultas e preservação de observações.
9. Preservação de Instagram confirmado e marca não contatar em atualização.
10. Reserva de chamadas, limites e recuperação sem repetir API.
11. Backup aberto como banco válido.
12. Demonstração sem chamadas externas.
13. Cancelamento antes do início.
14. Contrato HTTP Jev com respostas simuladas e rejeição de resposta inválida.
15. Instagram encontrado permanece candidato.
16. Seleção de empresas além da décima posição.
17. Falta de credenciais não produz dados fictícios em modo real.
18. Falha posterior preserva resultados parciais.
19. Proteção de fórmulas no CSV e filtros.
20. Fluxo HTTP de criação, processamento, edição, leitura persistida, exportação filtrada e exclusão.
21. Bloqueio de token inválido, origem externa e Host externo.
22. Rejeição de campanha real sem credenciais antes de enfileirar.
23. Arquivos estáticos e status sem exposição de chaves.

Vários cenários estão agrupados no mesmo teste. Os 25 testes incluem contratos simulados, não validação comercial do provedor.

## Ainda não verificado ao vivo

- Autenticação, saldo e permissões da conta DataForSEO.
- Disponibilidade efetiva do modelo Jev na conta do operador.
- Nome de localidade reconhecido pelo provedor para o primeiro piloto.
- Dados atuais e identidade das dez empresas reais.
- Tempo e custo reais por campanha.
- Inspeção visual/funcional em navegador de desktop e celular: infraestrutura de preview apropriada indisponível nesta execução. HTML e JavaScript foram validados por sintaxe e HTTP, mas isso não substitui um teste visual.
- Registro e execução de WebMCP em navegador compatível: não verificado em contexto real.
- Execução em Windows: instruções fornecidas; testes desta entrega rodaram em Linux.

Nenhuma mensagem foi enviada a empresas. Nenhuma consulta paga foi executada. Dados de demonstração não correspondem a locais reais.

## Próximo teste real

1. Abrir a demonstração e conferir interface, ficha, filtros, notas e exportação no próprio navegador.
2. Configurar as chaves no `.env` local e reiniciar.
3. Fazer uma campanha com três empresas e um termo, para validar credenciais e localidade com consumo limitado.
4. Conferir identidade, categoria, região, contatos e fontes; não confirmar Instagram apenas por nome parecido.
5. Ampliar para dez empresas e registrar erros, cobertura e custos antes de aumentar volume.

## Planejado, não implementado nesta versão

Navegação autônoma Jev/Chrome, extração direta de sites, importação CSV, grade geográfica ampliada com ausências explícitas, acompanhamento de ranking em séries históricas, agendamento, múltiplos usuários e envio automático de mensagens.
