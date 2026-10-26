export default {
  brand: 'Self-Service Fault Diagnosis',
  adminEntry: 'Admin',
  footer: 'Try the suggested steps first. If the problem persists, submit a ticket and we will contact you shortly.',

  home: {
    title: 'Self-Service Fault Diagnosis',
    subtitle: 'Pick your product, then the part, then the symptom — and get a fix in seconds',
    step1: '1. Select product',
    step2: '2. Select part',
    step3: '3. Select symptom',
    selectProduct: 'Select a product',
    selectPart: 'Select a product first',
    selectFault: 'Select a part first',
    keywordPlaceholder: 'Optional: filter by keyword, e.g. no spray, video dropout',
    productOption: '{name} ({model})',
    partOption: '{group} / {name}',
    viewSolution: 'View solution',
    foundCount:
      '{count} possible fault found — click to view the solution | {count} possible faults found — click to view the solution',
    symptomEmpty: 'No symptom description',
    noResult: 'No matching solution found',
    emptyTip: 'Try another keyword, or send the problem to us directly',
    submitTicket: 'Submit a ticket',
    initialTip: 'Select a product and a part to start',
    loadFailed: 'Failed to load',
    productLoadFailed: 'Failed to load products',
    partLoadFailed: 'Failed to load parts',
    faultLoadFailed: 'Failed to load faults',
    retrying: 'Retrying…'
  },

  faultDetail: {
    pageTitle: 'Solution',
    backHome: 'Back to home',
    retry: 'Retry',
    feedbackTitle: 'Did this solution solve your problem?',
    solved: 'Solved',
    unsolved: 'Not solved',
    stillNotWorking: 'Still not working — submit a ticket',
    thanksResolved: 'Thanks for the feedback. Glad it helped.',
    thanksUnresolved: 'Noted. We recommend submitting a ticket so an engineer can follow up.',
    notFound: 'This solution does not exist or has been unpublished',
    loadFailed: 'Failed to load',
    retryLater: 'Please try again later',
    feedbackMissing: 'Feedback context is missing. Please refresh the page.',
    feedbackExpired: 'This page is out of date. Refreshing…',
    feedbackFailed: 'Failed to submit feedback. Please try again.'
  },

  ticketNew: {
    pageTitle: 'Submit a ticket',
    related: 'Related problem',
    contact: 'Contact',
    contactPlaceholder: 'Phone or email so our engineer can reach you',
    name: 'Name',
    namePlaceholder: 'Optional, e.g. Mr. Zhang',
    description: 'Description',
    descriptionPlaceholder: 'Describe the symptom, what you have tried, and the machine model (at least 5 characters)',
    needOnSite: 'On-site service',
    needOnSiteText: 'I need an engineer to visit',
    submit: 'Submit ticket',
    back: 'Back',
    contactRequired: 'Please provide your contact information',
    contactLength: 'Contact must be between 5 and 100 characters',
    descriptionRequired: 'Please describe the problem',
    descriptionLength: 'Description must be between 5 and 2000 characters',
    tooFrequent: 'Too many submissions. Please try again later.',
    submitFailed: 'Submission failed. Please try again.'
  },

  ticketSuccess: {
    title: 'Ticket submitted',
    subtitle: 'We will contact you shortly. Please keep your phone available.',
    ticketNo: 'Ticket No.',
    copy: 'Copy',
    copied: 'Ticket number copied',
    copyFailed: 'Copy failed. Please write down the ticket number.',
    createdAt: 'Submitted at: {time}',
    backHome: 'Back to home'
  }
}
