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

## Validação em Windows e navegador — 16/10/2026

Ambiente: Windows 11, Python 3.14.2, Node 24.13, Playwright 1.64 com Chromium (desktop 1366×850 e celular emulado 390×844). Banco de teste em diretório temporário (`--data-dir`).

- Suíte unitária: **25/25 aprovados no Windows** após correção do backup.
- Teste de ponta a ponta no navegador: **19/19 verificações aprovadas** após correções: demonstração com 10 empresas e selo de dados fictícios, integrações sem chaves, busca, filtros de prioridade e etapa, ficha, notas e etapa salvas, persistência após recarregar, exportação CSV, backup pelo painel (`/api/backup` devolve SQLite válido), importação do JSON de modelo, recusa de coleta real sem credenciais (“Nenhuma busca foi iniciada”), estimativa de chamadas (3 empresas e 1 termo = até 4 chamadas), layout de celular sem alargamento e nenhum erro de JavaScript.

Defeitos encontrados e corrigidos (commit `baa5bbd`):

1. `Store.backup()` não fechava a conexão de destino; no Windows o arquivo ficava bloqueado e o backup falhava.
2. Opção “Alta” ausente no filtro de prioridade por uma tag `<option>` malformada.
3. No celular, o texto acessível do cabeçalho da tabela escapava da área rolável e alargava a página para 749 px.
4. Faltava `.gitignore`; `.env`, `data/` e `__pycache__/` agora são ignorados.

## Pendente: validação ao vivo com DataForSEO (adiada)

Status em 16/10/2026: **adiada** — o operador não conseguiu acessar a conta DataForSEO. Nenhuma consulta paga foi feita. Retomar com o roteiro abaixo.

1. Em app.dataforseo.com → **API Access**, copiar login e senha **da API** (diferentes do login do site) e conferir saldo.
2. `Copy-Item .env.example .env` e preencher `DATAFORSEO_LOGIN` e `DATAFORSEO_PASSWORD` (`TYPESAFE_API_KEY` é opcional).
3. `py -3 app.py` → em **Integrações**, o DataForSEO deve deixar de mostrar “Aguardando credenciais”.
4. Nova campanha → **Coleta real**, quantidade 3, um termo (ex.: `loja de roupa feminina São Carlos`), cidade `São Carlos,São Paulo,Brazil`. A estimativa deve indicar até 4 chamadas.
5. Se a localidade não for reconhecida, usar o ponto `-22.0174,-47.8909,14z` nos ajustes avançados.
6. Conferir manualmente identidade, endereço e telefone no Google Maps; não confirmar Instagram só por nome parecido.
7. Registrar mensagens de erro, custo informado e tempo; depois ampliar para 10 empresas (Fase C).

## Ainda não verificado ao vivo

- Autenticação, saldo e permissões da conta DataForSEO (ver seção acima).
- Disponibilidade efetiva do modelo Jev na conta do operador.
- Nome de localidade reconhecido pelo provedor para o primeiro piloto.
- Dados atuais e identidade das dez empresas reais.
- Tempo e custo reais por campanha.
- Registro e execução de WebMCP em navegador compatível: não verificado em contexto real.

Nenhuma mensagem foi enviada a empresas. Nenhuma consulta paga foi executada. Dados de demonstração não correspondem a locais reais.

## Planejado, não implementado nesta versão

Navegação autônoma Jev/Chrome, extração direta de sites, importação CSV, grade geográfica ampliada com ausências explícitas, acompanhamento de ranking em séries históricas, agendamento, múltiplos usuários e envio automático de mensagens.
