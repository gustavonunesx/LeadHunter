# Radar Local — plano do gerador de sites

Versão 0.1 · 16 de outubro de 2026 · Complementa `docs/PLANO_COMPLETO.md`

## 1. Resultado esperado

Na ficha de qualquer lead, o operador clica em **Criar site**. O Radar Local monta uma **prévia** de site de uma página para aquele estabelecimento, usando os dados coletados (nicho, endereço, telefone, avaliações, horários), as fotos disponíveis e uma análise visual feita por IA. A geração roda em segundo plano: o operador continua usando o painel e recebe um aviso quando a prévia fica pronta.

A prévia serve para a abordagem comercial: “fizemos um rascunho do seu site, quer ver?”. Ela **não é publicada** na internet nesta fase. A publicação só acontece depois do aceite do cliente e fica para uma etapa posterior.

O botão aparece em todos os leads. Para leads cujo site foi informado pela fonte, a ficha mostra um aviso (“esta empresa já tem site informado”) antes de confirmar, mas não bloqueia — a decisão é do operador.

## 2. Princípios

Herdados do plano principal e aplicados ao site:

1. **Nada inventado.** Nome, endereço, telefone, horários e nota entram no HTML **direto do banco, pelo código**, nunca escritos pela IA. A IA escreve apenas textos de apresentação e escolhe o design. Se um dado não existe, a seção é omitida ou marcada como `[confirmar com o cliente]`.
2. **Sem depoimentos, preços, anos de fundação ou prêmios fictícios.** A IA devolve uma lista de “afirmações a confirmar” para tudo que não veio dos dados.
3. **Prévia privada.** O site fica no computador do operador e só é aberto pelo painel local. Exportar ZIP é uma ação explícita do operador.
4. **Fontes e direitos de imagem registrados.** Cada foto guarda sua origem. Fotos de clientes publicadas em avaliações não são usadas. Fotos do Instagram entram somente quando o operador as adiciona manualmente (sem API privada nem raspagem do Instagram, como no plano principal).
5. **Saída da IA tratada como dado.** A IA nunca gera JavaScript nem HTML bruto: devolve JSON validado, e os templates locais escapam todo o texto.
6. **Custo visível e sem repetição automática.** Cada geração é registrada em `api_calls` com tokens e custo estimado; falhas não repetem chamadas pagas sozinhas.
7. **Testável sem chaves.** Leads de demonstração geram um site fictício offline, sem chamar a IA.

## 3. Jornada do operador

1. Abrir a ficha de um lead → seção **Site** → **Criar site**.
2. Um pequeno formulário mostra o material disponível e permite:
   - marcar/desmarcar fotos encontradas e **adicionar fotos** próprias (ex.: salvas do Instagram da loja);
   - escolher o objetivo principal (chamar no WhatsApp/telefone, visitar a loja, ver catálogo);
   - escrever instruções opcionais (“tom mais sofisticado”, “destacar moda plus size”);
   - ver o custo estimado e o limite diário.
3. Confirmar → a ficha pode ser fechada. No canto inferior direito aparece a bandeja **Sites em produção (1)** com o progresso: “Analisando fotos…”, “Escrevendo textos…”, “Montando páginas…”.
4. Ao terminar: aviso “Site de *Loja X* pronto — **Abrir prévia**”. A prévia abre em **nova aba** (`/sites/<id>/`), em tamanho real, testável em modo celular pelo próprio navegador.
5. Na ficha, a seção **Site** lista as versões com: Abrir prévia · Gerar nova versão com instruções · Baixar ZIP · Excluir · checklist de “afirmações a confirmar”.

**Por que bandeja + nova aba:** a bandeja não bloqueia o resto do painel e permite várias gerações em fila; a nova aba mostra o site como ele realmente será visto, sem a moldura de um modal. Um modal dentro da mesma janela seria apertado demais para avaliar um site inteiro.

## 4. Material de entrada

| Fonte | O que traz | Estado |
|---|---|---|
| Lead atual (Maps via DataForSEO, importação ou demonstração) | nome, categoria, endereço, cidade/bairro, telefone, site, nota, avaliações, link do Maps | Já implementado |
| Instagram confirmado | link do perfil, título e descrição do resultado indexado | Já implementado; usado só se `instagram_status = confirmed` |
| DataForSEO Maps (campos extras do mesmo resultado) | foto principal, total de fotos, horários, faixa de preço, descrição curta | **Confirmar na documentação** quais campos vêm no SERP de Maps; hoje não são gravados |
| DataForSEO Business Data — Google My Business Info | descrição do negócio, horários, atributos (acessibilidade, formas de pagamento etc.), fotos do proprietário | **1 chamada paga por lead; confirmar endpoint e custo**. Depende da validação ao vivo do DataForSEO, que está pendente |
| Fotos adicionadas pelo operador | imagens próprias da loja, inclusive salvas do Instagram | Novo: envio pela ficha |
| Sem fotos | layout tipográfico, com ilustração/ícones locais e paleta pelo nicho | Novo |

**Download de imagens:** o plano principal proíbe o servidor de acessar URLs arbitrárias. Para o site, abriremos uma exceção estreita: só domínios de imagem do Google em lista fixa (ex.: `lh3.googleusercontent.com`, `lh5.googleusercontent.com` — confirmar quais o DataForSEO devolve), apenas HTTPS, até 3 MB por imagem, no máximo 8 imagens, conferência dos bytes iniciais (JPEG/PNG/WebP) e sem seguir redirecionamentos para outros domínios.

## 5. Pipeline de geração

Executado por um **worker separado** do worker de campanhas, para que gerar sites não atrase buscas (e vice-versa).

1. **Preparar material** (local, sem custo): monta o dossiê do lead, baixa as fotos permitidas para `data/sites/<site_id>/assets/` e registra a origem de cada uma.
2. **Enriquecer** (opcional, pago, DataForSEO): Google My Business Info, se habilitado e se o lead tiver `place_id`. Ativado só depois da Fase C validar a conta.
3. **Analisar e escrever** (1 chamada ao Claude, com visão): recebe o dossiê + até 8 fotos e devolve um JSON validado por esquema (seção 6).
4. **Renderizar** (local): escolhe o template indicado, injeta os dados factuais do banco e os textos da IA com escape de HTML, gera `index.html`, `style.css` e as imagens otimizadas por tamanho.
5. **Verificar** (local, automático):
   - contraste da paleta pelo critério WCAG AA, com ajuste automático das cores que reprovarem;
   - todas as imagens referenciadas existem;
   - nenhum `<script>`, `on*=` ou URL não HTTP(S) no resultado;
   - telefone, endereço e nome no HTML são idênticos aos do banco;
   - tamanho total abaixo do limite.
6. **Concluir:** estado `completed` (ou `partial` com avisos), custo registrado, aviso no painel.

Estados do trabalho: `queued`, `running`, `completed`, `partial`, `failed`, `cancelled`, `interrupted` — os mesmos das campanhas. Cancelamento é cooperativo entre etapas; ao reiniciar o app, trabalhos em andamento ficam `interrupted` e **não** são refeitos sozinhos.

## 6. Uso do Claude

**Por que o Claude aqui e não o Jev:** o Jev foi adotado para classificações curtas. Criar o site exige análise de imagens, critério visual e redação em português, o que pede um modelo geral com visão.

| Decisão | Escolha | Motivo |
|---|---|---|
| Modelo | `claude-opus-5-5` (configurável por `SITE_MODEL`) | Melhor qualidade de redação e julgamento visual; o operador pode trocar para `claude-sonnet-5-5` se a qualidade se mantiver no piloto |
| Esforço | `output_config.effort = "high"` (configurável por `SITE_EFFORT`) | Tarefa criativa com várias restrições; o padrão do Opus 5.5 é `medium` e precisa ser definido explicitamente |
| Raciocínio | adaptativo (padrão do modelo; não é desativável no Opus 5.5) | — |
| Formato da resposta | Saídas estruturadas (`output_config.format` com JSON Schema) | Garante JSON válido; nada de HTML livre |
| Imagens | blocos `image` em base64 das fotos já baixadas | Evita que a IA busque URLs por conta própria e mantém o registro local |
| Cache de prompt | `cache_control` no prompt de sistema (diretrizes de design e redação, estável) | Reduz o custo de entrada quando vários sites são gerados em sequência |
| Recusa | parâmetro `fallbacks: "default"` (beta `server-side-fallback-2026-07-01`) e checagem de `stop_reason` antes de ler o conteúdo | Recomendado para o Opus 5.5; recusa vira estado `failed` com mensagem clara |
| Lote | API de Batches (50% do custo) **só** no futuro “gerar para selecionados” | O clique individual precisa de resposta em minutos; lote pode levar horas |
| Biblioteca | SDK oficial `anthropic` como **dependência opcional** | O app continua rodando só com a biblioteca padrão; o gerador com IA pede `pip install anthropic` e mostra isso em Integrações |

**Esquema de saída (resumo):**

```json
{
  "analise": {"publico": "...", "posicionamento": "...", "tom": "...", "observacoes_fotos": ["..."]},
  "design": {"template": "vitrine|editorial|minimal|servicos", "paleta": {"fundo": "#...", "texto": "#...", "destaque": "#...", "secundaria": "#..."}, "fontes": {"titulos": "...", "texto": "..."}},
  "conteudo": {"titulo": "...", "subtitulo": "...", "sobre": "...", "destaques": [{"titulo": "...", "texto": "..."}], "chamada": "...", "meta_descricao": "..."},
  "fotos": [{"arquivo": "foto-1.jpg", "uso": "capa|galeria|sobre|nao_usar", "texto_alternativo": "..."}],
  "afirmacoes_a_confirmar": ["..."]
}
```

As fontes ficam restritas a uma lista local de fontes livres; os templates rejeitam qualquer valor fora da lista. Cores inválidas caem para a paleta padrão do nicho.

**Proteção contra instruções embutidas:** nome, descrição e textos do Instagram vão marcados como dados não confiáveis no prompt (como já é feito com o Jev). Como a resposta é JSON com esquema e todo o texto é escapado, uma instrução maliciosa em um nome de loja não vira código.

## 7. Custos estimados

Estimativa por site, com preços de tabela do `claude-opus-5-5` (US$ 4 por milhão de tokens de entrada, US$ 20 por milhão de saída) — **a confirmar no piloto com o uso real registrado**:

| Item | Tokens aproximados | Custo aproximado |
|---|---:|---:|
| Prompt de sistema (cacheável) + dossiê | 5–7 mil | US$ 0,02–0,03 |
| 4–8 fotos | 6–12 mil | US$ 0,03–0,05 |
| Saída (JSON + raciocínio em esforço alto) | 10–25 mil | US$ 0,20–0,50 |
| **Total por site** | | **≈ US$ 0,25–0,60** |

Com `claude-sonnet-5-5` o custo cai para cerca de metade; com lote, metade de novo. O enriquecimento DataForSEO tem custo próprio, a confirmar. Limites configuráveis: `MAX_SITES_PER_DAY` (padrão 20) e reserva da chamada antes do envio, como nas campanhas.

## 8. Mudanças técnicas

**Banco** (`schema_version` 2, migração aditiva):

- `sites`: id, lead_id, campaign_id, version, state, progress, message, cancel_requested, options (JSON), brief (JSON da IA), checks (JSON), model, created_at, updated_at.
- `site_assets`: id, site_id, kind (`google`, `operator`, `generated`), source_url, local_path, mime, bytes, rights_note, used_as.
- `api_calls`: passa a aceitar `campaign_id` nulo e ganha `site_id`, para registrar o custo do site sem misturar com a campanha.

**Arquivos:** `data/sites/<site_id>/` com `index.html`, `style.css`, `assets/`. Já fica fora do Git pelo `.gitignore`.

**Código novo:**

- `radar/sites.py` — worker de sites, pipeline e verificações.
- `radar/site_templates/` — 3–4 templates HTML/CSS por estilo, sem JavaScript.
- `radar/providers.py` — adaptador `Claude` (SDK oficial) e, depois, `my_business_info` do DataForSEO.

**Rotas** (com as mesmas proteções de Host/Origin/token):

| Método | Rota | Uso |
|---|---|---|
| POST | `/api/leads/<id>/sites` | Cria trabalho (opções, fotos escolhidas, instruções) |
| POST | `/api/leads/<id>/assets` | Envia fotos do operador (JSON base64, até 2 MB cada, 8 MB no total) |
| GET | `/api/sites` | Lista para a bandeja (em andamento e recentes) |
| GET | `/api/sites/<id>` | Detalhe, progresso, checklist |
| POST | `/api/sites/<id>/cancel` | Cancelar |
| DELETE | `/api/sites/<id>` | Excluir versão e arquivos |
| GET | `/sites/<id>/…` | Prévia estática, com `Content-Security-Policy: default-src 'self'; script-src 'none'` |
| GET | `/api/sites/<id>/download` | ZIP da versão |

**Painel:** seção **Site** na ficha, diálogo de criação, bandeja de produção (consulta a cada 2 s enquanto houver trabalho ativo, aproveitando o ciclo de atualização existente) e aviso de conclusão com link para a prévia. Status do Claude na tela de Integrações.

**Configuração (`.env`):** `ANTHROPIC_API_KEY`, `SITE_MODEL=claude-opus-5-5`, `SITE_EFFORT=high`, `MAX_SITES_PER_DAY=20`, `SITE_ENRICH_GMB=false`.

## 9. Fases

| Fase | Entrega | Depende de | Aceite |
|---|---|---|---|
| **S1 — Base offline** | Tabelas, worker, rotas, bandeja, prévia em nova aba, templates e gerador **sem IA** (textos fixos por nicho) para leads de demonstração e importados | Nada | Fluxo completo no navegador sem chaves; testes automáticos e Playwright passam |
| **S2 — Claude** | Adaptador com visão e saídas estruturadas, envio de fotos pelo operador, custos em `api_calls`, limite diário, verificações automáticas | Chave Anthropic | 5 sites de leads reais conferidos: nenhum dado factual divergente, nenhuma afirmação sem marcação, contraste AA, celular sem quebra |
| **S3 — Fotos e dados do Google** | Campos extras do Maps + My Business Info; download com lista de domínios | **Validação ao vivo do DataForSEO (pendente)** | Origem de cada foto registrada; nenhum download fora da lista |
| **S4 — Produtividade** | Nova versão com instruções, comparação de versões, ZIP, miniatura por Playwright, “gerar para selecionados” via lote | S2 | Operador gera 10 prévias em sequência sem travar o painel |
| **S5 — Publicação (futuro)** | Publicar após aceite do cliente (hospedagem estática, domínio, formulário de contato) | Demanda comercial e termo de aceite | Fora do escopo agora |

## 10. Testes necessários

- Dados factuais no HTML são exatamente os do banco; ausentes não aparecem inventados.
- Resposta da IA fora do esquema, recusa ou corte por limite de tokens → `failed`/`partial` com mensagem, sem site quebrado.
- Texto malicioso no nome do lead (`<script>`, `"><img onerror=…>`, instrução para a IA) aparece escapado na prévia.
- Prévia servida com CSP sem scripts; nenhum `<script>` no HTML gerado.
- Download de imagem fora da lista, com redirecionamento externo, acima do limite ou com tipo falso é recusado.
- Cancelamento, reinício e limite diário não disparam chamadas repetidas.
- Worker de sites não bloqueia campanha em andamento.
- Contraste AA corrigido automaticamente quando a paleta da IA reprovar.
- Playwright: criar site da demonstração, continuar navegando, receber aviso, abrir a prévia em desktop e celular.

## 11. Riscos e decisões em aberto

| Risco | Tratamento |
|---|---|
| Direito de uso das fotos | Prévia privada; origem registrada; fotos de clientes não usadas; publicação só com aceite do dono |
| IA “enfeitar” com fatos falsos | Fatos inseridos pelo código; lista de afirmações a confirmar; checklist na ficha |
| Sites todos parecidos | 3–4 templates, paleta e tipografia escolhidas pela análise das fotos; ajustar após o piloto |
| Custo crescer com volume | Limite diário, custo visível por site, opção Sonnet e lote |
| Lead já tem site | Aviso antes de criar; pode servir como proposta de redesenho |
| Instagram sem API | Fotos só por envio manual do operador |

**Decisões a validar com o operador antes da S2:**

1. Quais objetivos de contato oferecer: só telefone (`tel:`), ou também WhatsApp quando o operador confirmar que o número é WhatsApp?
2. O ZIP exportado deve incluir uma página “prévia — não oficial” ou ir limpo?
3. Orçamento mensal máximo para geração de sites.
