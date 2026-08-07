# Relatório de Conformidade — RGPD e Regulamento de IA

Avaliação técnica da aplicação Vitarerum face ao Regulamento (UE) 2016/679
(RGPD) e ao Regulamento (UE) 2024/1689 (Regulamento de IA).

| | |
|---|---|
| **Data** | 7 de agosto de 2026 |
| **Âmbito** | `vitarerum-api`, `vitarerum-ui`, configuração de implantação (`docs/cloud`, `cloudbuild.yaml`) |
| **Ramo analisado** | `cryptography` |
| **Método** | Inspeção estática do código-fonte e da configuração de implantação |

## Ressalva

Este é um relatório de **engenharia**, não um parecer jurídico. As conclusões
descrevem o que está — ou não está — implementado no código. Diversas
obrigações do RGPD cumprem-se fora do repositório: registo de atividades de
tratamento, contratos de subcontratação, avaliação de impacto, designação de
encarregado de proteção de dados. Quando este relatório diz que algo "não
existe", significa **não existe no código**; não significa que não exista na
organização.

A qualificação definitiva do sistema e das bases legais aplicáveis deve ser
confirmada por assessoria jurídica, em especial quanto à natureza da instituição
(organismo público ou entidade privada), que altera obrigações relevantes.

## Sumário executivo

Foram identificados **catorze problemas**, sendo onze relativos ao RGPD e três
ao Regulamento de IA.

O quadro geral é assimétrico. No RGPD há **ausências estruturais**: mecanismos
inteiros exigidos pelo regulamento não existem na aplicação — apagamento,
conservação limitada, acesso do titular. No Regulamento de IA a situação é
substancialmente melhor: a arquitetura de rastreabilidade necessária **já
existe** e o problema é de exposição, não de conceção.

A conclusão mais relevante do lado do Regulamento de IA é negativa no bom
sentido: o sistema **não é de alto risco** (ver secção "Enquadramento no
Regulamento de IA"), o que reduz drasticamente as obrigações aplicáveis.

### Índice de problemas

| ID | Referência legal | Problema | Gravidade |
|---|---|---|---|
| [RGPD-01](#rgpd-01) | Art. 17 | Direito ao apagamento não implementado | Crítica |
| [RGPD-02](#rgpd-02) | Art. 5(1)(e) | Sem limitação da conservação | Crítica |
| [RGPD-03](#rgpd-03) | Art. 44-49, Art. 9 | Transferência internacional sem salvaguarda documentada | Crítica |
| [RGPD-04](#rgpd-04) | Art. 13 | Informação ao titular insuficiente | Crítica |
| [RGPD-05](#rgpd-05) | Art. 7 | Consentimento provavelmente inválido | Crítica |
| [RGPD-06](#rgpd-06) | Art. 15, 20 | Acesso e portabilidade não implementados | Grave |
| [RGPD-07](#rgpd-07) | Art. 32, 5(1)(f) | Segurança e disponibilidade dos anexos | Grave |
| [RGPD-08](#rgpd-08) | Art. 30 | Registo de atividades de tratamento ausente | Grave |
| [RGPD-09](#rgpd-09) | Art. 33, 34 | Sem trilha de acesso a dados pessoais | Moderada |
| [RGPD-10](#rgpd-10) | Art. 25, 35 | Proteção desde a conceção e AIPD | Moderada |
| [RGPD-11](#rgpd-11) | Art. 32 | Risco residual de registo de credenciais | Baixa |
| [IA-01](#ia-01) | Art. 50(4) | Texto de IA publicado sem divulgação | Grave |
| [IA-02](#ia-02) | Art. 50(2) | Sem marcação legível por máquina | Moderada |
| [IA-03](#ia-03) | Art. 4 | Literacia em IA não formalizada | Moderada |

---

# Parte I — RGPD

<a id="rgpd-01"></a>
## RGPD-01 — Direito ao apagamento não implementado

**Gravidade:** Crítica

### Referência legal

**Artigo 17.º** — Direito ao apagamento dos dados («direito a ser esquecido»).
O titular tem o direito de obter do responsável pelo tratamento o apagamento dos
seus dados pessoais, sem demora injustificada, nomeadamente quando os dados
deixaram de ser necessários para a finalidade que motivou a recolha ou quando o
titular retira o consentimento.

### Problema encontrado

Nenhum ponto final da API apaga os dados pessoais de um cidadão. Os métodos
`DELETE` existentes cobrem anexos, modelos de documento e associações a grupos —
nenhum remove `PublicProposalSubmissionRecord` ou `MuseumQuestionRecord`.

Um pedido de apagamento só pode hoje ser satisfeito com SQL manual em produção,
o que não é auditável nem reproduzível.

O problema é agravado pela dispersão dos dados pessoais por tabelas satélite,
que replicam ou referenciam a informação do titular:

- `use_of_collections/infrastructure/models.py:375` — `ProposalEventRecord`
- `use_of_collections/infrastructure/models.py:466,481` — `ConversationRecord`, `MessageRecord`
- `public_submission/infrastructure/models.py:67` — `requester_email` em `ProposalAmendmentTokenRecord`
- `museum_questions/infrastructure/models.py:23-26` — `requester_name`, `requester_email`, `subject`, `message`

Mesmo o apagamento manual dificilmente seria completo.

### Recomendação

1. Implementar um caso de uso `ErasePersonalData` que receba um identificador de
   titular (e-mail ou identificador de submissão) e apague, numa única
   transação, todas as tabelas que contêm dados desse titular.
2. Escrever primeiro o **inventário de tabelas afetadas** e mantê-lo como teste
   automatizado: um teste que falhe sempre que uma nova coluna de dados pessoais
   seja acrescentada sem entrar no caminho de apagamento. Sem isto, a
   funcionalidade degrada-se silenciosamente à medida que o modelo cresce.
3. Onde a eliminação total colidir com obrigações de conservação legítimas
   (por exemplo, registo contabilístico de um projeto executado), aplicar
   **anonimização irreversível** em vez de eliminação — substituir nome e e-mail
   por marcadores, preservando a integridade referencial.
4. Expor a operação a um perfil administrativo, com registo de quem a executou
   e quando.

---

<a id="rgpd-02"></a>
## RGPD-02 — Sem limitação da conservação

**Gravidade:** Crítica

### Referência legal

**Artigo 5.º, n.º 1, alínea e)** — Princípio da limitação da conservação. Os
dados devem ser conservados de forma a permitir a identificação dos titulares
apenas durante o período necessário para as finalidades do tratamento.

### Problema encontrado

Não existe qualquer lógica de conservação, expurgo ou anonimização na
aplicação. A varredura por `retention`, `purge`, `anonymi`, `cleanup` e termos
equivalentes em `app/` não devolve nenhuma implementação.

Os registos de token possuem `expires_at`, mas a expiração é apenas um critério
de **validação** — nada os elimina:

- `identity/infrastructure/models.py:79` — `PasswordResetTokenRecord.expires_at`
- `public_submission/infrastructure/models.py:70` — `ProposalAmendmentTokenRecord.expires_at`, acompanhado de `requester_email` na linha 67

O efeito prático é que dados pessoais recolhidos hoje permanecerão na base de
dados indefinidamente, incluindo os de submissões nunca confirmadas — que nunca
chegaram sequer a gerar um tratamento útil.

### Recomendação

1. Definir e documentar uma **política de conservação por categoria de dados**.
   Proposta inicial, a validar juridicamente:

   | Categoria | Prazo sugerido |
   |---|---|
   | Submissões públicas não confirmadas | 30 dias |
   | Tokens expirados ou utilizados | 30 dias |
   | Perguntas ao museu respondidas e encerradas | 2 anos |
   | Propostas indeferidas | 2 anos |
   | Projetos de uso executados | Conforme obrigação arquivística da instituição |

2. Implementar uma tarefa de expurgo agendada. Sendo a implantação em Cloud Run,
   o mecanismo natural é um **Cloud Scheduler** a invocar um Cloud Run Job,
   reaproveitando o padrão já usado para as migrações em `cloudbuild.yaml`.
3. Registar cada execução do expurgo — número de registos afetados por tabela —
   como prova de cumprimento nos termos do Art. 5.º, n.º 2.
4. Prioridade imediata e de baixo custo: eliminar tokens expirados. É a categoria
   com maior volume, menor valor e risco mais direto, por associar um endereço
   de correio eletrónico a uma credencial de uso único.

---

<a id="rgpd-03"></a>
## RGPD-03 — Transferência internacional sem salvaguarda documentada

**Gravidade:** Crítica

### Referência legal

**Artigos 44.º a 49.º** — Transferências de dados pessoais para países
terceiros. A transferência só é lícita mediante decisão de adequação (Art. 45.º)
ou garantias adequadas (Art. 46.º).

**Artigo 28.º** — O tratamento por subcontratante deve reger-se por contrato que
vincule o subcontratante ao responsável.

**Artigo 9.º** — Tratamento de categorias especiais de dados pessoais.

### Problema encontrado

O texto livre submetido pelo cidadão é enviado a um serviço de terceiro fora da
União Europeia para efeitos de triagem automática:

- `docs/cloud/vitarerum-cloudrun.env.example.yaml:2` — `OLLAMA_BASE_URL: https://ollama.com`
- `ai/museum_question_triage/infrastructure/model_ollama.py:287` — método `classify(self, message: str)`, que transmite a mensagem ao modelo

O campo de mensagem admite até 4000 caracteres de texto livre
(`museum_questions/presentation/schemas.py:25`) sem qualquer advertência ao
cidadão para não incluir informação sensível. Consequentemente, o conteúdo
transmitido pode conter dados das categorias especiais do Art. 9.º — por
exemplo, num pedido de acessibilidade que revele dados de saúde.

Adicionalmente, a própria residência dos dados é extracomunitária: o serviço é
implantado em `us-east1` (`cloudbuild.yaml:2`).

Não há, no repositório, contrato de subcontratação, avaliação de transferência
nem menção deste destinatário na informação prestada ao titular.

### Recomendação

Tratar os dois destinatários separadamente, porque o estado de conformidade é
diferente:

**Google Cloud (Cloud Run, Cloud SQL).** Verificar e arquivar a documentação de
conformidade existente — as cláusulas contratuais-tipo do fornecedor e a sua
certificação ao abrigo do EU-US Data Privacy Framework cobrem tipicamente este
cenário. É provável que seja um problema de **documentação em falta**, não de
ilicitude. Ponderar ainda a migração para uma região da UE, que elimina a
questão na origem e tem custo de execução baixo.

**Ollama.** Aqui o risco é real e não documentado. Três opções, por ordem de
preferência:

1. **Auto-hospedar o modelo.** A aplicação já suporta esta configuração —
   `ollama_api_key` vazio aponta para uma instância local
   (`config.py:41`). Elimina a transferência por completo e é a opção mais
   limpa.
2. **Pseudonimizar antes do envio.** Remover nome e endereço eletrónico do texto
   antes da chamada. Mitiga, mas não elimina: o corpo da mensagem pode conter
   identificadores indiretos.
3. **Formalizar a relação.** Contrato nos termos do Art. 28.º, avaliação de
   impacto da transferência, e inclusão do destinatário na política de
   privacidade.

Em qualquer cenário, acrescentar advertência no formulário público a pedir que
o cidadão não inclua dados sensíveis, e documentar a triagem automática na
informação prestada nos termos do Art. 13.º.

---

<a id="rgpd-04"></a>
## RGPD-04 — Informação ao titular insuficiente

**Gravidade:** Crítica

### Referência legal

**Artigo 13.º** — Informação a facultar quando os dados são recolhidos junto do
titular. Inclui a identidade do responsável, os contactos do encarregado de
proteção de dados, as finalidades e a base jurídica, os destinatários, as
transferências para países terceiros, o prazo de conservação, os direitos do
titular e o direito de reclamação junto da autoridade de controlo.

### Problema encontrado

A informação prestada ao cidadão resume-se a uma frase junto à caixa de
consentimento:

> *"I agree that Vitarerum may process the personal data in this form to handle
> my question."*
>
> — `vitarerum-ui/src/app/features/public/ask-museum/ask-museum-page.component.html:105-107`

Não existe política de privacidade. A verificação de `src/app/app.routes.ts`
confirma a ausência de rota e de componente correspondentes.

Falta, portanto, a quase totalidade dos elementos obrigatórios: identidade do
responsável, base jurídica, prazo de conservação, destinatários — incluindo o
serviço de IA referido em [RGPD-03](#rgpd-03) —, direitos do titular, contacto
do encarregado de proteção de dados e direito de reclamação.

### Recomendação

1. Criar uma página de política de privacidade em rota pública
   (`/privacidade`), acessível sem autenticação, e ligá-la a partir de **ambos**
   os formulários públicos e do rodapé.
2. Cobrir explicitamente a triagem por IA e o destinatário extracomunitário. É o
   ponto mais provável de omissão e o de maior exposição.
3. Substituir a frase do consentimento por uma remissão informada: *"Li e
   compreendi a [política de privacidade]"*, com hiperligação.
4. Versionar o texto da política e registar, em cada submissão, a versão em
   vigor no momento — necessário para [RGPD-05](#rgpd-05).

---

<a id="rgpd-05"></a>
## RGPD-05 — Consentimento provavelmente inválido

**Gravidade:** Crítica

### Referência legal

**Artigo 7.º** — Condições aplicáveis ao consentimento. O n.º 1 exige que o
responsável possa **demonstrar** que o titular consentiu. O n.º 3 estabelece que
retirar o consentimento deve ser tão fácil como dá-lo. O n.º 4 determina que, ao
avaliar se o consentimento é livre, se deve ponderar se a execução do serviço
foi condicionada ao consentimento.

**Artigo 6.º, n.º 1** — Licitude do tratamento, incluindo a alínea e), exercício
de funções de interesse público.

### Problema encontrado

Três deficiências independentes:

**O consentimento não é livre.** O campo é obrigatório para submeter — declarado
como `consent: Literal[True]` em `public_submission/presentation/schemas.py:34`
e em `museum_questions/presentation/schemas.py:25`. Sem o assinalar, o cidadão
não pode contactar o museu. Isto colide diretamente com o Art. 7.º, n.º 4.

**Não há retirada.** Nenhum mecanismo permite ao cidadão retirar o
consentimento, ao contrário do exigido pelo Art. 7.º, n.º 3.

**Não é demonstrável.** Persiste-se apenas um booleano
(`public_submission/infrastructure/models.py:31`). Não se regista a versão do
texto aceite nem o instante do consentimento, pelo que não é possível demonstrar
*a que* o titular consentiu.

### Recomendação

A recomendação de fundo é **mudar a base legal**, não corrigir o consentimento.

Para uma instituição museológica, o tratamento de um pedido de informação ou de
uma proposta de uso do acervo enquadra-se com naturalidade no **interesse
público (Art. 6.º, n.º 1, alínea e))** ou no interesse legítimo. É a base
adequada quando o tratamento é necessário para prestar o próprio serviço que o
cidadão solicitou.

Esta alteração resolve simultaneamente os três problemas: deixa de haver
consentimento condicionado, deixa de ser necessário um mecanismo de retirada, e
a demonstração passa a ser documental em vez de por registo individual.

Passos concretos:

1. Confirmar a base legal com assessoria jurídica, atendendo à natureza da
   instituição.
2. Substituir a caixa de consentimento por uma **declaração informativa** com
   remissão para a política de privacidade — reconhecimento, não autorização.
3. Manter consentimento apenas onde for genuinamente opcional e separável, como
   comunicações de divulgação não relacionadas com o pedido.
4. Caso se mantenha o consentimento, registar versão do texto e data, e
   implementar retirada por hiperligação com token, à semelhança do mecanismo de
   confirmação já existente.

---

<a id="rgpd-06"></a>
## RGPD-06 — Acesso e portabilidade não implementados

**Gravidade:** Grave

### Referência legal

**Artigo 15.º** — Direito de acesso do titular aos dados pessoais e a informação
sobre finalidades, destinatários e prazo de conservação.

**Artigo 20.º** — Direito de portabilidade: receber os dados em formato
estruturado, de uso corrente e de leitura automática.

### Problema encontrado

Nenhum ponto final devolve ao cidadão o conjunto de dados que a instituição
detém a seu respeito.

O único acesso concedido ao titular é o fluxo de correção por token, que expõe
exclusivamente os itens dentro do âmbito de correção — tudo o resto responde
`OUT_OF_SCOPE` (`public_submission/presentation/routes.py:462`). É um mecanismo
de edição delimitada, não de acesso.

### Recomendação

1. Implementar um ponto final autenticado por token, análogo ao fluxo de
   confirmação já existente, que devolva o conjunto completo de dados do titular
   em JSON — satisfazendo simultaneamente os Art. 15.º e 20.º.
2. Reaproveitar o inventário de tabelas construído para
   [RGPD-01](#rgpd-01): acesso e apagamento percorrem exatamente o mesmo
   conjunto de dados. Implementados em conjunto, o custo marginal do segundo é
   reduzido.
3. Incluir os metadados exigidos pelo Art. 15.º, n.º 1 — finalidades,
   destinatários, prazo de conservação — e não apenas os dados em bruto.

---

<a id="rgpd-07"></a>
## RGPD-07 — Segurança e disponibilidade dos anexos

**Gravidade:** Grave

### Referência legal

**Artigo 32.º** — Segurança do tratamento, incluindo a alínea a) do n.º 1
(cifragem) e a alínea b) (capacidade de assegurar confidencialidade,
integridade, **disponibilidade** e resiliência).

**Artigo 5.º, n.º 1, alínea f)** — Integridade e confidencialidade.

**Artigo 5.º, n.º 2** — Responsabilidade pela demonstração do cumprimento.

### Problema encontrado

Dois problemas distintos, sendo o segundo mais grave que o primeiro.

**Ausência de cifragem ao nível da aplicação.** Os ficheiros são gravados em
claro (`use_of_collections/infrastructure/file_storage.py:37-43`) e as colunas
com dados pessoais não são cifradas. A cifragem em repouso do fornecedor de
nuvem protege contra subtração física do suporte, mas não contra extração
lógica da base de dados nem contra credencial comprometida.

**Perda silenciosa de anexos.** A configuração de produção declara um
armazenamento que não existe no código:

- `docs/cloud/vitarerum-cloudrun.env.example.yaml:10-11` — `GCS_BUCKET_NAME` e `FILE_STORAGE_BACKEND: gcs`
- Não existe qualquer implementação de armazenamento em GCS na aplicação
- `config.py:90` — `extra="ignore"` faz com que estas variáveis sejam descartadas sem aviso
- Consequentemente, todas as injeções resolvem para `LocalDiskFileStorage(settings.data_dir)`, apontando para `/app/data` (`Dockerfile:41`)

Em Cloud Run, `/app/data` reside no sistema de ficheiros **efémero** do
contentor. Os documentos submetidos por cidadãos são eliminados a cada nova
revisão, reinício ou redução de escala para zero.

Trata-se de perda de dados pessoais que nenhum mecanismo detetaria — falha
simultânea de disponibilidade (Art. 32.º) e de responsabilidade (Art. 5.º,
n.º 2).

### Recomendação

**Primeiro, a disponibilidade.** É o problema mais grave e independente da
cifragem:

1. Implementar `GcsFileStorage` respeitando o protocolo `FileStorage` já
   definido nos quatro contextos.
2. Acrescentar `file_storage_backend` e `gcs_bucket_name` a `Settings` e
   **validar em `validate_non_local_security`** que o armazenamento local não é
   utilizado fora de ambiente local. A ausência desta validação foi a causa
   direta de o problema ter passado despercebido.

**Depois, a cifragem.** A arquitetura existente torna-a barata:

1. `EncryptedFileStorage` como invólucro do protocolo `FileStorage`, delegando
   no armazenamento real. **AES-256-GCM** com cifragem em envelope: chave de
   dados aleatória por ficheiro, protegida por uma chave mestra no Secret
   Manager. Com aceleração por hardware, o custo é desprezável para o limite de
   25 MiB configurado, e a operação já corre em thread separada.
2. Nas colunas, um `TypeDecorator` de SQLAlchemy aplicado **seletivamente** aos
   campos com dados pessoais. Não cifrar indiscriminadamente: cada coluna
   cifrada inutiliza o respetivo índice. Para `citizen_email`, que é indexado e
   pesquisável, acrescentar um índice cego —
   `HMAC-SHA256(chave, minúsculas(email))` — em coluna adjacente, ou empregar
   cifragem determinística (AES-GCM-SIV).
3. Não alterar `password_hash` (bcrypt) nem `token_hash` (SHA-256). São funções
   de dispersão, não cifragem, e estão corretas.

---

<a id="rgpd-08"></a>
## RGPD-08 — Registo de atividades de tratamento ausente

**Gravidade:** Grave

### Referência legal

**Artigo 30.º** — Registos das atividades de tratamento. A dispensa prevista no
n.º 5 para entidades com menos de 250 trabalhadores **não se aplica** quando o
tratamento não é ocasional ou abrange categorias especiais de dados.

### Problema encontrado

Não existe registo de atividades de tratamento no repositório.

A dispensa do n.º 5 não é invocável: o tratamento é sistemático e contínuo, e o
campo de texto livre pode receber categorias especiais, conforme analisado em
[RGPD-03](#rgpd-03). Sendo a instituição um organismo público — comum no setor
museológico —, a obrigação é incondicional.

### Recomendação

1. Elaborar o registo cobrindo, no mínimo, as atividades identificadas nesta
   análise: submissão pública de propostas, perguntas ao museu, gestão de
   utilizadores internos, triagem assistida por IA e publicação externa.
2. Colocá-lo sob controlo de versões, em `docs/legal/`, junto deste relatório. O
   registo tem de acompanhar a evolução do sistema; mantido fora do repositório,
   desatualiza-se.
3. Aproveitar o inventário de tabelas de [RGPD-01](#rgpd-01) como base factual
   das categorias de dados a declarar.

---

<a id="rgpd-09"></a>
## RGPD-09 — Sem trilha de acesso a dados pessoais

**Gravidade:** Moderada

### Referência legal

**Artigo 33.º** — Notificação de violação de dados pessoais à autoridade de
controlo no prazo de 72 horas.

**Artigo 34.º** — Comunicação da violação ao titular.

### Problema encontrado

Não existe registo de quem acedeu a que dados pessoais e quando.

`ObjectAccessLogRecord` (`use_of_collections/infrastructure/models.py:123`)
regista acessos a **objetos do acervo**, não a dados pessoais — apesar da
semelhança de nome, não cumpre esta função.

Sem esta trilha, perante suspeita de violação é impossível determinar o âmbito
— que titulares foram afetados — e, por conseguinte, cumprir o prazo de 72 horas
ou avaliar a necessidade de comunicação aos titulares.

### Recomendação

1. Registar os acessos de leitura a dados pessoais de cidadãos: identificador do
   utilizador interno, recurso consultado, instante. Aplicar às listagens e
   detalhes de submissões públicas e de perguntas ao museu.
2. Manter a trilha **separada** dos dados operacionais e sujeita a conservação
   própria — tipicamente entre seis meses e dois anos.
3. Registar apenas identificadores, nunca o conteúdo consultado. Uma trilha de
   auditoria que replique dados pessoais amplia a superfície de exposição em vez
   de a reduzir.
4. Documentar o procedimento interno de resposta a violações, incluindo quem
   decide sobre a notificação e em que prazo.

---

<a id="rgpd-10"></a>
## RGPD-10 — Proteção desde a conceção e avaliação de impacto

**Gravidade:** Moderada

### Referência legal

**Artigo 25.º** — Proteção de dados desde a conceção e por defeito.

**Artigo 35.º** — Avaliação de impacto sobre a proteção de dados, exigida quando
o tratamento é suscetível de implicar risco elevado, nomeadamente em caso de
avaliação sistemática com recurso a tratamento automatizado.

### Problema encontrado

O campo de mensagem aceita 4000 caracteres de texto livre sem qualquer
orientação quanto ao que não deve ser incluído
(`museum_questions/presentation/schemas.py:25`). É simultaneamente o campo com
maior probabilidade de conter dados sensíveis e o que é transmitido ao serviço
de IA externo.

Não há indício, no repositório, de que tenha sido realizada avaliação de
impacto. A combinação de triagem automatizada de dados de cidadãos com
transferência para país terceiro corresponde ao perfil que habitualmente a
desencadeia.

### Recomendação

1. Realizar uma avaliação de impacto centrada na triagem por IA. Esta análise
   pode servir-lhe de base factual.
2. Acrescentar orientação no formulário público: indicar o tipo de informação
   necessária e advertir para não incluir dados de saúde ou outros dados
   sensíveis.
3. Reavaliar a minimização dos dados recolhidos. Concretamente:
   `citizen_name` é necessário, ou bastaria o endereço eletrónico para a
   correspondência?

---

<a id="rgpd-11"></a>
## RGPD-11 — Risco residual de registo de credenciais

**Gravidade:** Baixa

### Referência legal

**Artigo 32.º** — Segurança do tratamento.

### Problema encontrado

`LoggingConfirmationEmailSender` regista em log o endereço eletrónico e o token
de confirmação:

- `public_submission/infrastructure/email.py:41` — `logger.info("[public-submission] confirmation link for %s: %s", to_email, link)`
- Idem na linha 51, para a hiperligação de correção

O comportamento **está mitigado em produção**: `validate_non_local_security`
(`config.py:160`) exige `smtp_host` configurado fora de ambiente local ou de
teste, pelo que este remetente não é instanciado.

Regista-se como risco residual por depender integralmente dessa validação.

### Recomendação

1. Manter a validação e acrescentar um comentário no remetente que a refira
   explicitamente como salvaguarda, evitando que seja removida por
   desconhecimento.
2. Considerar truncar o token no registo, mesmo em ambiente local. O elo perde
   utilidade para depuração se apenas o endereço for registado, mas deixa de ser
   uma credencial completa em texto claro.

---

# Parte II — Regulamento de IA

## Enquadramento no Regulamento de IA

A determinação do nível de risco condiciona todas as obrigações subsequentes,
pelo que se apresenta em primeiro lugar.

**O sistema não corresponde a nenhuma prática proibida (Art. 5.º).** Não há
identificação biométrica, reconhecimento de emoções, classificação social nem
técnicas manipulativas.

**O sistema não é de alto risco (Art. 6.º e Anexo III).** O ponto do Anexo III
que mais se aproximaria — n.º 5, alínea a), relativo à avaliação da
elegibilidade para prestações e serviços públicos essenciais — abrange
segurança social, cuidados de saúde, habitação e serviços de emergência. O
tratamento de pedidos de informação sobre um acervo museológico não se enquadra
nessa categoria.

**Existe intervenção humana em todas as decisões**, o que é determinante e está
verificado no código:

- `museum_questions/application/use_cases.py:257` — `require_staff(data.caller)` em `MarkMuseumQuestionOutOfScope`
- `museum_questions/application/use_cases.py:267` — o fundamento (`reason`) é redigido por pessoal, não gerado
- Todos os pontos finais de IA exigem `require_staff`, tanto na triagem como na narrativa

A IA **sugere**; a decisão é humana. Isto mantém o sistema fora do alto risco e,
adicionalmente, afasta a aplicação do **Art. 22.º do RGPD** (decisões
individuais automatizadas) — que constituiria um problema sério caso a triagem
indeferisse pedidos autonomamente.

**Enquadramento resultante:** risco mínimo, com obrigações de **transparência
(Art. 50.º)** e de **literacia (Art. 4.º)**.

**Calendário de aplicação relevante:**

| Data | Disposições aplicáveis |
|---|---|
| 2 de fevereiro de 2025 | Art. 4.º (literacia) e Art. 5.º (proibições) |
| 2 de agosto de 2025 | Modelos de uso geral, governação, sanções |
| **2 de agosto de 2026** | **Aplicação geral, incluindo o Art. 50.º** |

O Art. 50.º tornou-se aplicável cinco dias antes da data deste relatório.

---

<a id="ia-01"></a>
## IA-01 — Texto de IA publicado sem divulgação

**Gravidade:** Grave

### Referência legal

**Artigo 50.º, n.º 4** — Os responsáveis pela implantação de sistemas de IA que
gerem ou manipulem texto publicado com a finalidade de informar o público sobre
questões de interesse público devem divulgar que o conteúdo foi artificialmente
gerado. A obrigação **não se aplica** quando o conteúdo tenha sido objeto de
revisão humana ou de controlo editorial, e exista responsabilidade editorial
atribuída a uma pessoa singular ou coletiva.

### Problema encontrado

Narrativas geradas por modelo de linguagem são disponibilizadas publicamente sem
qualquer indicação da sua origem.

O percurso completo:

1. `external_publications/presentation/routes.py:265` — o ponto final
   `GET /{token}` é **não autenticado**
2. `reports/public.py:93-95` — a resposta inclui `PublishedNarrativeView`,
   construída a partir de `narrative.data.narrative`, texto produzido pelo
   modelo
3. `external_publications/presentation/routes.py:397-402` — o
   `ExternalNarrativeResponse` transporta apenas `id` e `text`

O aspeto mais notável é que **a proveniência existe e é descartada**. O registo
em base de dados guarda a informação necessária:

- `ai/museum_narrative/infrastructure/models.py:43` — `llm_model`
- Linhas 36-47 — `resolution_source`, `creativity_temperature`, `generated_at`, `prompt_version`

A informação está persistida e é perdida exatamente na fronteira em que a lei a
exige.

**Quanto à isenção por responsabilidade editorial:** foi verificada e **não se
encontra estabelecida**. O critério de elegibilidade para publicação é
`status="CIDOC_CONFORMANT"` (`reports/public.py:143`) — conformidade semântica
do mapeamento CIDOC-CRM, e não revisão editorial do texto. Existe edição de
narrativa (`ai/museum_narrative/presentation/routes.py:306`) e histórico de
revisões, mas nada impõe revisão prévia à publicação nem regista quem assumiu a
responsabilidade pelo conteúdo.

### Recomendação

Duas medidas, complementares. Recomenda-se a adoção de ambas.

**1. Propagar a proveniência até à resposta pública.**

Acrescentar a `ExternalNarrativeResponse` os campos já persistidos —
`generatedByAi`, `model`, `generatedAt` — e apresentá-los na interface com
formulação clara: *"Texto gerado com assistência de inteligência artificial."*

É uma alteração contida: os dados existem, trata-se de os transportar através de
duas camadas.

**2. Instituir revisão editorial como condição de publicação.**

Acrescentar um estado de revisão à narrativa, com revisor identificado e data,
e exigi-lo em `CreateExternalPublication` antes de admitir a publicação.

Esta medida aciona a isenção do Art. 50.º, n.º 4 e melhora o produto
independentemente da obrigação legal — publicar texto de modelo de linguagem sem
revisão humana é, para uma instituição museológica, um risco reputacional
autónomo.

A divulgação continua recomendável mesmo com revisão instituída, por ser a
prática honesta perante o público.

---

<a id="ia-02"></a>
## IA-02 — Sem marcação legível por máquina

**Gravidade:** Moderada

### Referência legal

**Artigo 50.º, n.º 2** — Os fornecedores de sistemas de IA que gerem conteúdo
sintético de áudio, imagem, vídeo ou **texto** devem assegurar que os resultados
sejam marcados em formato legível por máquina e detetáveis como artificialmente
gerados.

### Problema encontrado

A instituição constrói um sistema de IA sobre um modelo de uso geral e coloca-o
em serviço em nome próprio, assumindo por isso o papel de **fornecedor de
sistema de IA** na aceção do Art. 3.º — e não apenas o de responsável pela
implantação.

O documento JSON-LD publicado em
`external_publications/presentation/routes.py:294` não contém qualquer marcação
que assinale a narrativa como gerada por IA.

### Recomendação

1. Assinalar a proveniência no JSON-LD já emitido. É o local natural: o formato
   é legível por máquina por definição e já faz parte do contrato público.
2. O vocabulário CIDOC-CRM, já adotado, permite exprimir a atividade de geração
   e o agente que a executou, evitando a introdução de um esquema próprio.
3. Implementar em conjunto com [IA-01](#ia-01) — é a mesma informação, exposta
   em dois formatos.

---

<a id="ia-03"></a>
## IA-03 — Literacia em IA não formalizada

**Gravidade:** Moderada

### Referência legal

**Artigo 4.º** — Literacia no domínio da IA. Os fornecedores e os responsáveis
pela implantação devem tomar medidas para assegurar um nível suficiente de
literacia em IA do seu pessoal, tendo em conta os conhecimentos técnicos, a
experiência e o contexto de utilização. Aplicável desde 2 de fevereiro de 2025,
independentemente do nível de risco.

### Problema encontrado

Existe um princípio de cumprimento, e é genuíno: o painel *"How AI assistance
works"* explica ao funcionário que a triagem **estima** o âmbito e **rascunha**
uma resposta
(`vitarerum-ui/src/app/features/museum-questions/pages/detail/museum-question-detail-page.component.html:383-390`).
A formulação é adequada, por descrever a funcionalidade como assistência e não
como decisão.

Falta, porém, a componente organizacional que o artigo exige: medidas de
formação registadas para quem utiliza a ferramenta, e documentação das
limitações conhecidas — propensão a alucinação, desempenho desigual entre
línguas, e o facto de a triagem operar sobre texto livre não estruturado.

### Recomendação

1. Elaborar um documento breve de limitações conhecidas do sistema, dirigido ao
   pessoal utilizador, e mantê-lo em `docs/legal/` ou no manual de utilizador
   existente.
2. Registar a formação ministrada — data, participantes, conteúdos. O artigo
   exige medidas, e as medidas devem ser demonstráveis.
3. Ampliar o painel existente com as limitações, aproximando-o do ponto de
   utilização. É o local onde a informação tem maior probabilidade de ser lida.

---

# Parte III — Aspetos já conformes

Registam-se os elementos que se encontram corretamente implementados, quer por
serem relevantes para a demonstração de conformidade, quer para evitar
alterações desnecessárias.

**Segurança de credenciais.** Palavras-passe protegidas com bcrypt
(`identity/infrastructure/security.py:22`) e tokens com SHA-256
(`shared/tokens.py:14`). São funções de dispersão, adequadas ao fim, e **não
devem ser substituídas por cifragem**.

**Minimização de endereços IP.** Tratados apenas em memória para limitação de
frequência (`public_submission/infrastructure/rate_limiter.py:1-5`) e
protegidos por dispersão quando persistidos
(`external_publications/presentation/routes.py:431`).

**Confirmação em duplo passo.** A submissão pública exige confirmação por
correio eletrónico antes de o tratamento prosseguir, o que constitui boa prática
de verificação da identidade do titular.

**Validação de conteúdo carregado.** Verificação por assinatura binária em vez
de extensão (`shared/uploads.py:94-111`) e prevenção de travessia de diretórios
no armazenamento (`file_storage.py:26-29`).

**Rastreabilidade da IA.** Proveniência completa persistida por narrativa —
modelo, versão do prompt, temperatura, instante de geração — acompanhada de
`payload_hash` e relatório de validação CIDOC. As classificações de triagem
conservam a versão do classificador, o que permite auditar deriva ao longo do
tempo.

Esta última é a razão pela qual a conformidade com o Regulamento de IA é
alcançável a baixo custo: **a arquitetura pressuposta pelo Art. 50.º já existe**.
O que falta é expô-la.

---

# Parte IV — Plano de mitigação recomendado

A ordenação seguinte reflete risco regulatório, e não esforço de implementação.

## Fase 1 — Documental (esforço reduzido, risco elevado)

| Ação | Problemas resolvidos |
|---|---|
| Política de privacidade em rota pública | [RGPD-04](#rgpd-04) |
| Revisão da base legal, de consentimento para interesse público | [RGPD-05](#rgpd-05) |
| Registo de atividades de tratamento | [RGPD-08](#rgpd-08) |
| Documento de limitações da IA e registo de formação | [IA-03](#ia-03) |

Não exige alterações de código relevantes e elimina quatro problemas, dois deles
de gravidade crítica.

## Fase 2 — Disponibilidade e transparência (esforço reduzido, em curso)

| Ação | Problemas resolvidos |
|---|---|
| `GcsFileStorage` e validação em `validate_non_local_security` | [RGPD-07](#rgpd-07), parte |
| Proveniência de IA na resposta pública e no JSON-LD | [IA-01](#ia-01), [IA-02](#ia-02) |

O armazenamento é prioritário por existir **perda ativa de dados**. A divulgação
de IA é prioritária por a obrigação estar em vigor desde 2 de agosto de 2026 e o
remendo ser reduzido.

## Fase 3 — Direitos dos titulares (esforço elevado, estrutural)

| Ação | Problemas resolvidos |
|---|---|
| Inventário de dados pessoais como teste automatizado | Base das seguintes |
| Caso de uso de apagamento e anonimização | [RGPD-01](#rgpd-01) |
| Ponto final de acesso e portabilidade | [RGPD-06](#rgpd-06) |
| Expurgo agendado com política de conservação | [RGPD-02](#rgpd-02) |

As três funcionalidades percorrem o mesmo conjunto de tabelas. Implementadas em
conjunto sobre um inventário comum, o custo é substancialmente inferior à soma
das partes.

## Fase 4 — Transferências e avaliação

| Ação | Problemas resolvidos |
|---|---|
| Decisão sobre o Ollama: auto-hospedagem, pseudonimização ou contrato | [RGPD-03](#rgpd-03) |
| Verificação documental das salvaguardas do Google Cloud | [RGPD-03](#rgpd-03) |
| Avaliação de impacto sobre a triagem por IA | [RGPD-10](#rgpd-10) |

## Fase 5 — Reforço

| Ação | Problemas resolvidos |
|---|---|
| Revisão editorial obrigatória antes da publicação | [IA-01](#ia-01), isenção |
| Cifragem de ficheiros e colunas seletivas | [RGPD-07](#rgpd-07), parte |
| Trilha de acesso a dados pessoais | [RGPD-09](#rgpd-09) |
| Truncagem de tokens em registo | [RGPD-11](#rgpd-11) |

## Nota sobre a prioridade da cifragem

A cifragem ao nível da aplicação é o tema mais visível, mas **não é o mais
urgente**. Surge na Fase 5 por três razões:

1. A cifragem em repouso do fornecedor de nuvem já cobre parte do risco.
2. Os problemas [RGPD-01](#rgpd-01) e [RGPD-02](#rgpd-02) falham por **ausência
   total de mecanismo**, e não por implementação insuficiente — é o que uma
   autoridade de controlo verifica em primeiro lugar.
3. A perda de anexos descrita em [RGPD-07](#rgpd-07) é um problema de
   disponibilidade mais grave do que a ausência de cifragem, e resolve-se
   primeiro.

Cifrar ficheiros que estão a ser perdidos não melhora a posição de conformidade.
