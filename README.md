# Radar Local

Aplicativo local para encontrar e qualificar empresas por nicho e região. Painel em português, banco SQLite, coleta configurável de Google Maps, busca de Instagram, classificação com Jev, histórico e exportação CSV.

**Esta entrega é o MVP local funcional.** O fluxo offline foi testado. As integrações de API foram testadas com respostas simuladas; nenhuma consulta paga ou campanha real foi executada nesta entrega. Navegação autônoma Jev/Chrome está na próxima fase, não neste aplicativo.

## Começar no Windows

Requisito: Python 3.11 ou superior instalado. Não é necessário instalar pacotes Python, Node, n8n ou banco separado.

1. Extraia o ZIP para uma pasta, por exemplo `C:\dev\radar-local`.
2. Abra essa pasta no terminal.
3. Execute:

```powershell
py -3 app.py
```

4. Abra **http://127.0.0.1:8765** no navegador desse mesmo computador.
5. Clique em **Explorar demonstração**. As dez empresas são fictícias e não consomem APIs.

Também é possível abrir `INICIAR_WINDOWS.bat`. Mantenha o terminal aberto enquanto usa o painel. Ctrl+C encerra o aplicativo. Ao abrir de novo, campanhas, notas e revisões permanecem salvas.

Se o comando `py` não existir, instale Python pelo [site oficial](https://www.python.org/downloads/) ou tente `python app.py` se ele já estiver no PATH.

## Linux ou macOS

```bash
python3 app.py
```

Abra o mesmo endereço local. Para usar outra porta:

```bash
python3 app.py --port 8766
```

## Ativar coleta real

No Windows:

```powershell
Copy-Item .env.example .env
```

No Linux/macOS:

```bash
cp .env.example .env
```

Edite `.env` no seu computador:

```dotenv
DATAFORSEO_LOGIN=seu_login_da_api
DATAFORSEO_PASSWORD=sua_senha_da_api
TYPESAFE_API_KEY=sua_chave_typesafe
TYPESAFE_MODEL=jev-1.13.0
MAX_CALLS_PER_CAMPAIGN=80
MAX_CALLS_PER_DAY=200
```

Não envie essas credenciais pelo chat. A senha DataForSEO é a credencial de API exibida na conta. A chave Jev é opcional: sem ela, a classificação usa regras locais identificadas no painel. O navegador recebe somente o estado de configuração, nunca as chaves.

Reinicie o aplicativo após alterar o `.env`. Em **Nova campanha**, escolha **Coleta real**. Comece com três empresas, um termo e uma localidade reconhecida pelo DataForSEO. Exemplo de formato: `São Carlos,São Paulo,Brazil`. Se o provedor não reconhecer o nome, use um ponto `latitude,longitude,zoom` nos ajustes avançados ou consulte a lista de localidades da conta. O aplicativo não valida a existência dessa localidade offline.

As credenciais, disponibilidade do modelo e o saldo precisam ser validados no seu ambiente. O código fixa os endpoints públicos documentados; não utiliza API privada de Instagram nem cookies.

## O que acontece na campanha

1. Consulta até três termos e até três pontos, com profundidade de pelo menos 30 resultados por busca.
2. Exclui anúncios e resultados com cidade estruturada diferente da solicitada.
3. Reúne candidatos, remove duplicados e seleciona até o limite informado pela pontuação preliminar. Não escolhe apenas os primeiros resultados.
4. Usa Jev, quando configurado e selecionado, para qualificar o nicho de cada selecionado.
5. Opcionalmente procura até três candidatos de Instagram numa consulta web por empresa. **Candidato não é identidade confirmada.**
6. Calcula prioridade comercial e posição mediana observada separadamente.
7. Salva fontes, observações, notas e etapas. Resultados parciais continuam disponíveis em falhas.

O nicho e a região são filtros de pesquisa, não garantia de que toda empresa retornada corresponde ao perfil. Classificação incerta vai para revisão. Porte fiscal, receita, intenção de contratar e saúde financeira não são inferidos.

## Revisar Instagram e acompanhar leads

Abra a ficha pelo nome da empresa. Compare nome, cidade, telefone e vínculos oficiais antes de usar **Confirmar identidade**. Você pode corrigir a URL manualmente. A confirmação é registrada como revisão do operador. **Rejeitar candidato** evita tratá-lo como um contato disponível.

O telefone é mostrado como comercial informado, sem presumir WhatsApp. Marque a etapa e registre suas observações. A marca **Não contatar** permanece quando o mesmo lugar aparece em outra campanha. O app não envia mensagens em nenhuma etapa.

## Importar dados próprios

Clique em **Importar JSON** e baixe o modelo. Substitua os valores de exemplo por dados reais que você tenha autorização para utilizar. O arquivo tem este formato:

```json
{
  "config": {
    "niche": "Loja de moda feminina",
    "city": "São Carlos,São Paulo,Brazil",
    "service": "google"
  },
  "leads": [
    {
      "name": "Nome da empresa",
      "category": "Loja de moda feminina",
      "address": "Endereço da empresa",
      "city": "São Carlos",
      "phone": null,
      "website": null,
      "instagram": null,
      "rating": null,
      "reviews": null,
      "source_url": null
    }
  ]
}
```

Limites: 100 empresas e 1 MB por arquivo. Nome e endereço são obrigatórios; cidade usa o valor da campanha se não informada. `service` aceita `google`, `website` e `marketing`. Importações não chamam APIs e não presumem posições no Google. Instagram importado começa como candidato. É possível complementar o contato na ficha. Importação CSV é uma melhoria futura; **exportação CSV já está implementada**.

## Entender os resultados

- **Prioridade**: heurística de 0–100, com razões visíveis, independente do ranking. Em revisão e fora do perfil prevalecem sobre a nota numérica.
- **Visibilidade**: mediana apenas das posições observadas. Acima de 10 é baixa na amostra; sem posição é não medida. Não mede cobertura total.
- **Avaliações**: contagem ausente fica desconhecida; só há comparação com a mediana quando existem pelo menos cinco empresas com nicho correspondente e contagem conhecida na seleção final.
- **Site**: quando a fonte foi consultada e não informou URL, isso é sinal para conferir, não prova de que a empresa não tem site. Em importação, campo vazio sozinho não rende pontos de necessidade.
- **Marketing digital**: usa sinais de descoberta local; não analisa publicações, seguidores ou anúncios nesta versão.

Leia `docs/PLANO_COMPLETO.md` para os pesos e a evolução prevista. A seleção pode deixar de fora empresas não encontradas pelo provedor. Instagram indexado pode estar desatualizado ou pertencer a um homônimo.

## Custos, cancelamento e falhas

O formulário estima número máximo de chamadas, não preço final. Cada tentativa é reservada antes da requisição e conta para os limites. Um único worker processa campanhas em sequência. O limite diário usa UTC; as datas do painel aparecem no fuso de São Paulo.

Custos retornados pelo DataForSEO e tokens de entrada Jev aparecem separados. A falta de um valor monetário não significa gratuidade. A aplicação não calcula uma fatura total nem oferece teto monetário garantido; use limites do provedor quando disponíveis.

Não há retry automático de chamadas pagas. Ao cancelar, a chamada já em andamento pode terminar; novas etapas são interrompidas. Em reinício durante uma execução, o estado passa a interrompido e não se repete a cobrança automaticamente. Para tentar novamente, crie uma nova campanha de forma deliberada.

Mensagens de credencial, saldo, nome de localidade e rede indicam falha real; o aplicativo nunca substitui uma campanha real por dados fictícios.

## Backup e restauração

Use o botão de download no rodapé lateral do painel para baixar um backup consistente. Alternativamente, com o aplicativo fechado, copie `data/radar.sqlite3`.

Para restaurar:

1. Feche o aplicativo.
2. Faça uma cópia de segurança da pasta `data` atual.
3. Mova os arquivos atuais `radar.sqlite3`, `radar.sqlite3-wal` e `radar.sqlite3-shm`, quando existirem, para outra pasta. Não misture arquivos WAL antigos com o backup.
4. Copie o backup como `data/radar.sqlite3`.
5. Inicie novamente e confira as campanhas.

O banco contém os contatos e suas notas; o `.env` precisa de proteção separada. Não coloque o banco nem as chaves num repositório público.

## Verificação

```bash
python3 -m unittest discover -s tests -v
```

No Windows, substitua `python3` por `py -3`. Para conferir a sintaxe do frontend, se tiver Node instalado: `node --check web/app.js`.

Os testes usam dados fictícios, mocks e servidor HTTP local efêmero. Não consomem créditos de serviços externos. Consulte `docs/VALIDACAO.md` para os resultados da entrega.

## Arquitetura e arquivos

```text
app.py                 API HTTP e inicialização local
radar/domain.py        validação, identidade e pontuação
radar/storage.py       SQLite, campanhas, observações e consumo
radar/providers.py     conectores DataForSEO e TypeSafe
radar/engine.py        fila e processamento
web/                   painel HTML/CSS/JavaScript
tests/                 testes offline
docs/                  plano completo e relatório de validação
.env.example           configuração sem segredos
```

O app liga exclusivamente em `127.0.0.1`, confere Host/Origin e exige token para alterações. Há limite de payload, consultas SQL parametrizadas, escape de HTML e proteção contra fórmulas no CSV. Nenhuma URL arbitrária encontrada é acessada pelo servidor: chamadas externas usam somente endpoints fixos dos provedores.

Este servidor é para operação local individual. Não o exponha diretamente à internet; uma versão hospedada exigirá autenticação, HTTPS, isolamento de usuários e outro servidor de produção. A escolha local também permite evoluir futuramente para o worker de navegador sem enviar sua sessão a um servidor.

## Uso de dados

Avalie condições de coleta, armazenamento e retenção dos fornecedores antes do piloto real. Um intermediário não concede automaticamente direitos irrestritos sobre todas as fontes. A API oficial Places não foi integrada como um diretório exportável irrestrito. Registre apenas informações comerciais necessárias, corrija dados e respeite pedidos de não contato.

## Próximo marco

Validar uma campanha pequena real e conferir manualmente os resultados. Depois disso, comparar coleta via API com uma prova de conceito Jev/Chrome, conforme o plano. A versão atual não contém a navegação autônoma nem uma promessa de ranking ou conversão.
