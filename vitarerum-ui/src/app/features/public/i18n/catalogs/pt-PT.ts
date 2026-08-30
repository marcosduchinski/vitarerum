import { PublicI18nCatalog } from '../public-i18n.model';

/**
 * Source catalogue. Orthography: Acordo Ortográfico de 1990 ("objeto",
 * "coleções", "ativo") — apply it consistently when adding entries.
 */
export const PT_PT_CATALOG = {
  'public.appName': 'Vitarerum',

  'public.shell.home': 'Vitarerum — início',
  'public.shell.language': 'Idioma',
  'public.shell.language.pt-PT': 'Português',
  'public.shell.language.en': 'Inglês',

  'public.routes.landing': 'Vitarerum',
  'public.routes.askMuseum': 'Pergunte ao Museu',
  'public.routes.askMuseumReceived': 'Pergunta recebida',
  'public.routes.submitProposal': 'Submeter um pedido',
  'public.routes.submissionReceived': 'Pedido recebido',
  'public.routes.submissionConfirm': 'Confirme o seu pedido',
  'public.routes.submissionEdit': 'Corrija os seus documentos',

  'public.landing.eyebrow': 'Bem-vindo',
  'public.landing.title': 'Como podemos ajudar?',
  'public.landing.description':
    'Escolha a opção que melhor corresponde ao que precisa — uma pergunta rápida, ou um pedido formal de acesso às nossas coleções.',
  'public.landing.askMuseum.title': 'Pergunte ao Museu',
  'public.landing.askMuseum.description':
    'Tem uma pergunta simples sobre as nossas coleções, em especial sobre visitas in situ para investigação? Pergunte aqui e respondemos por e-mail.',
  'public.landing.submitProposal.title': 'Pedir uma visita in situ',
  'public.landing.submitProposal.description':
    'Submeta um pedido formal de acesso às nossas coleções, com datas, documentos comprovativos e confirmação.',

  'public.askMuseum.eyebrow': 'Pergunte ao Museu',
  'public.askMuseum.title': 'Pergunte ao Museu',
  'public.askMuseum.description':
    'Tem uma pergunta rápida? Diga-nos quem é e o que gostaria de saber — respondemos por e-mail.',
  'public.askMuseum.scopeNotice':
    'De momento, o Pergunte ao Museu está disponível apenas para perguntas sobre o uso de coleções, em especial visitas in situ para investigação. Perguntas sobre exposições, empréstimos, eventos, atividades educativas ou outros serviços do museu serão encerradas com uma resposta por e-mail.',
  'public.askMuseum.form.name.label': 'Nome completo',
  'public.askMuseum.form.name.required': 'O seu nome é obrigatório.',
  'public.askMuseum.form.email.label': 'E-mail',
  'public.askMuseum.form.email.placeholder': 'nome@exemplo.pt',
  'public.askMuseum.form.email.invalid': 'É obrigatório um endereço de e-mail válido.',
  'public.askMuseum.form.email.hint': 'É para aqui que enviamos a nossa resposta.',
  'public.askMuseum.form.subject.label': 'Assunto',
  'public.askMuseum.form.subject.placeholder': 'Assunto em poucas palavras',
  'public.askMuseum.form.subject.required': 'O assunto é obrigatório.',
  'public.askMuseum.form.message.label': 'Mensagem',
  'public.askMuseum.form.message.placeholder': 'Escreva a sua pergunta…',
  'public.askMuseum.form.message.required': 'A sua pergunta é obrigatória.',
  'public.askMuseum.form.images.label': 'Imagens',
  'public.askMuseum.form.images.listLabel': 'Imagens selecionadas',
  'public.askMuseum.form.images.remove': 'Remover {{name}}',
  'public.askMuseum.form.images.hint':
    'Opcional: até 10 imagens PNG ou JPEG, 5 MB cada, 25 MB no total.',
  'public.askMuseum.form.images.selected.one': '{{count}} imagem selecionada · {{size}} no total',
  'public.askMuseum.form.images.selected.other':
    '{{count}} imagens selecionadas · {{size}} no total',
  'public.askMuseum.form.images.tooMany': 'Anexe no máximo {{count}} imagens.',
  'public.askMuseum.form.images.invalidType': 'Só são aceites imagens PNG e JPEG.',
  'public.askMuseum.form.images.tooLarge': 'Cada imagem não pode exceder 5 MB.',
  'public.askMuseum.form.images.totalTooLarge': 'As imagens anexadas não podem exceder 25 MB no total.',
  'public.askMuseum.form.consent.label':
    'Concordo que o Vitarerum trate os dados pessoais deste formulário para dar seguimento à minha pergunta.',
  'public.askMuseum.form.consent.required': 'É obrigatório dar consentimento para submeter.',
  'public.askMuseum.form.captcha.required': 'Conclua a verificação, por favor.',
  'public.askMuseum.form.submit': 'Enviar pergunta',
  'public.askMuseum.form.submitting': 'A enviar…',

  'public.askMuseum.received.title': 'Pergunta recebida',
  'public.askMuseum.received.message':
    'Obrigado pela sua pergunta. Recebemo-la e responderemos logo que possível.',
  'public.askMuseum.received.messageTo':
    'Obrigado pela sua pergunta. Recebemo-la e responderemos para {{email}} logo que possível.',
  'public.askMuseum.received.note': 'Respondemos por e-mail. Enviou sem querer? Não precisa de fazer nada —',
  'public.askMuseum.received.noteLink': 'faça outra pergunta',

  'public.submitProposal.eyebrow': 'Submissão pública',
  'public.submitProposal.title': 'Submeter um pedido',
  'public.submitProposal.description':
    'Qualquer cidadão pode pedir acesso às nossas coleções. Diga-nos quem é e do que precisa — enviamos-lhe por e-mail uma ligação para confirmar o pedido.',
  'public.submitProposal.sections.details': 'Os seus dados',
  'public.submitProposal.sections.request': 'O seu pedido',
  'public.submitProposal.sections.requestHint':
    'O seu pedido abre uma conversa com a equipa de coleções. Descreva a que pretende aceder e porquê.',
  'public.submitProposal.form.name.label': 'Nome completo',
  'public.submitProposal.form.name.required': 'O seu nome é obrigatório.',
  'public.submitProposal.form.email.label': 'E-mail',
  'public.submitProposal.form.email.placeholder': 'nome@exemplo.pt',
  'public.submitProposal.form.email.invalid': 'É obrigatório um endereço de e-mail válido.',
  'public.submitProposal.form.email.hint':
    'É para aqui que enviamos a ligação de confirmação. O pedido só segue depois de o confirmar.',
  'public.submitProposal.form.useType.label': 'Utilização pretendida',
  'public.submitProposal.form.useType.placeholder': 'Escolha como vai utilizar a coleção…',
  'public.submitProposal.form.useType.required': 'Escolha como vai utilizar a coleção.',
  'public.submitProposal.form.useType.unsupported':
    'De momento só estão operacionais os pedidos de visita in situ. Exposição e outras utilizações serão implementadas mais tarde.',
  'public.submitProposal.useTypes.IN_SITU_VISIT': 'Visita in situ',
  'public.submitProposal.useTypes.EXHIBITION': 'Exposição',
  'public.submitProposal.useTypes.OTHER': 'Outra',
  'public.submitProposal.templates.title': 'Documentos obrigatórios',
  'public.submitProposal.templates.intro':
    'Descarregue os modelos abaixo, preencha-os e anexe os ficheiros preenchidos ao seu pedido.',
  'public.submitProposal.templates.mandatory': 'Obrigatório',
  'public.submitProposal.form.dates.label': 'Datas propostas',
  'public.submitProposal.form.dates.from': 'De',
  'public.submitProposal.form.dates.to': 'A',
  'public.submitProposal.form.dates.required': 'Indique a data de início e a de fim.',
  'public.submitProposal.form.dates.invalidRange':
    'A data de fim não pode ser anterior à de início.',
  'public.submitProposal.form.dates.hint': 'Quando gostaria de aceder à coleção?',
  'public.submitProposal.form.subject.label': 'Assunto',
  'public.submitProposal.form.subject.placeholder': 'Assunto em poucas palavras',
  'public.submitProposal.form.subject.required': 'O assunto é obrigatório.',
  'public.submitProposal.form.body.label': 'Mensagem',
  'public.submitProposal.form.body.placeholder': 'Apresente-se e descreva do que precisa…',
  'public.submitProposal.form.body.required': 'O corpo da mensagem é obrigatório.',
  'public.submitProposal.form.documents.label': 'Documentos comprovativos',
  'public.submitProposal.form.documents.listLabel': 'Documentos comprovativos selecionados',
  'public.submitProposal.form.documents.remove': 'Remover',
  'public.submitProposal.form.documents.hint':
    'Anexe 1 a 5 ficheiros. São aceites PDF, JPG, PNG e DOCX, até 10 MB cada.',
  'public.submitProposal.form.documents.required': 'Anexe pelo menos um documento comprovativo.',
  'public.submitProposal.form.documents.tooMany':
    'Não anexe mais do que cinco documentos comprovativos.',
  'public.submitProposal.form.documents.tooLarge': '{{name}} excede os 10 MB.',
  'public.submitProposal.form.documents.invalidType':
    '{{name}} não é um tipo de ficheiro suportado.',
  'public.submitProposal.form.consent.label':
    'Concordo que o Vitarerum trate os dados pessoais deste formulário para dar seguimento ao meu pedido.',
  'public.submitProposal.form.consent.required': 'É obrigatório dar consentimento para submeter.',
  'public.submitProposal.form.captcha.required': 'Conclua a verificação, por favor.',
  'public.submitProposal.form.submit': 'Submeter pedido',
  'public.submitProposal.form.submitting': 'A submeter…',

  'public.submitProposal.received.title': 'Quase — verifique a sua caixa de entrada',
  'public.submitProposal.received.message':
    'Enviámos uma ligação de confirmação. Clique nela para encaminhar o seu pedido à equipa de coleções. A ligação expira em 24 horas.',
  'public.submitProposal.received.messageTo':
    'Enviámos uma ligação de confirmação para {{email}}. Clique nela para encaminhar o seu pedido à equipa de coleções. A ligação expira em 24 horas.',
  'public.submitProposal.received.note':
    'Não recebeu o e-mail? Pode demorar alguns minutos. Verifique a pasta de spam ou',
  'public.submitProposal.received.noteLink': 'faça um novo pedido',

  'public.submitProposal.confirm.loading': 'A confirmar o seu pedido…',
  'public.submitProposal.confirm.startNew': 'Fazer um novo pedido',
  'public.submitProposal.confirm.CONFIRMED.title': 'Pedido confirmado',
  'public.submitProposal.confirm.CONFIRMED.message':
    'Obrigado — o seu pedido foi encaminhado para a equipa de coleções, que responderá para o seu e-mail.',
  'public.submitProposal.confirm.ALREADY_CONFIRMED.title': 'Já confirmado',
  'public.submitProposal.confirm.ALREADY_CONFIRMED.message':
    'Este pedido já tinha sido confirmado. A equipa de coleções tem-no — não é preciso fazer mais nada.',
  'public.submitProposal.confirm.EXPIRED.title': 'Ligação expirada',
  'public.submitProposal.confirm.EXPIRED.message':
    'Esta ligação de confirmação expirou. Submeta o pedido novamente para receber uma ligação nova.',
  'public.submitProposal.confirm.INVALID.title': 'Ligação inválida',
  'public.submitProposal.confirm.INVALID.message':
    'Não foi possível confirmar este pedido. A ligação pode estar incompleta. Submeta o pedido novamente.',

  'public.submitProposal.edit.loading': 'A carregar o seu pedido de correção…',
  'public.submitProposal.edit.startNew': 'Fazer um novo pedido',
  'public.submitProposal.edit.submitted.title': 'Documentos submetidos',
  'public.submitProposal.edit.submitted.message':
    'Obrigado. A equipa de coleções recebeu os seus documentos corrigidos.',
  'public.submitProposal.edit.conflict.title': 'Este pedido já não pode ser editado',
  'public.submitProposal.edit.conflict.message':
    'O pedido já seguiu em frente. Contacte a equipa de coleções se tiver dúvidas.',
  'public.submitProposal.edit.invalid.title': 'Ligação inválida ou expirada',
  'public.submitProposal.edit.invalid.message':
    'Esta ligação de correção é inválida, expirou ou já foi utilizada.',
  'public.submitProposal.edit.eyebrow': 'Correção de documentos',
  'public.submitProposal.edit.title': 'Corrija os seus documentos',
  'public.submitProposal.edit.description':
    'O pedido {{reference}} aguarda as alterações de documentos indicadas abaixo.',
  'public.submitProposal.edit.summaryLabel': 'Resumo do pedido de correção',
  'public.submitProposal.edit.status': 'Estado: {{status}}',
  'public.submitProposal.edit.expires': 'A ligação expira: {{date}}',
  'public.submitProposal.edit.replaceDocument': 'Substituir documento',
  'public.submitProposal.edit.attachMissingDocument': 'Anexar documento em falta',
  'public.submitProposal.edit.uploaded': 'Carregado',
  'public.submitProposal.edit.remove': 'Remover',
  'public.submitProposal.edit.removing': 'A remover…',
  'public.submitProposal.edit.replacementFile': 'Ficheiro de substituição',
  'public.submitProposal.edit.documentFile': 'Ficheiro do documento',
  'public.submitProposal.edit.fileHint': 'Formatos aceites: PDF, JPG, PNG ou DOCX, até 10 MB.',
  'public.submitProposal.edit.upload': 'Carregar ficheiro',
  'public.submitProposal.edit.uploading': 'A carregar…',
  'public.submitProposal.edit.noPending.title': 'Sem correções de documentos pendentes',
  'public.submitProposal.edit.noPending.message':
    'Não há correções de documentos em aberto para esta ligação.',
  'public.submitProposal.edit.submit': 'Submeter documentos corrigidos',
  'public.submitProposal.edit.submitting': 'A submeter…',
  'public.submitProposal.edit.file.tooLarge': '{{name}} excede os 10 MB.',
  'public.submitProposal.edit.file.invalidType': '{{name}} não é um tipo de ficheiro suportado.',

  'public.submitProposal.statuses.REQUESTED': 'Pedida',
  'public.submitProposal.statuses.RESOLVED': 'Resolvida',
  'public.submitProposal.statuses.PENDING_DOCUMENTS': 'Documentos pendentes',
  'public.submitProposal.statuses.SUBMITTED': 'Submetido',
} as const satisfies PublicI18nCatalog;
