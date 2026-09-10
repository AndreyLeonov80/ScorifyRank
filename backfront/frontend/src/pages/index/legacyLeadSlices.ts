export type MessagesSliceState = {
  messagesLimit: number;
  messageRenderStart: number;
  messageRenderSize: number;
  messageRenderWindowSize: number;
  messagesLoadingMore: boolean;
  messagesLoadedOffset: number;
};

export type ChatAnalysisSliceState = {
  running: boolean;
  error: string;
  progressPercent: number;
  progressStatus: string;
  progressEtaSec: number;
};

export type LeadAuthSliceState = {
  authLoading: boolean;
  authForm: {
    apiId: string;
    apiHash: string;
    phone: string;
    code: string;
    password: string;
  };
};

export type LlmAnswersSliceState = {
  llmRunning: boolean;
  llmHtml: string;
  llmProgress: {
    running: boolean;
    percent: number;
    etaSec: number;
    status: string;
    error: string;
  };
};

export function createMessagesSliceState(): MessagesSliceState {
  return {
    messagesLimit: 30,
    messageRenderStart: 0,
    messageRenderSize: 30,
    messageRenderWindowSize: 30,
    messagesLoadingMore: false,
    messagesLoadedOffset: 0,
  };
}

export function createChatAnalysisSliceState(): ChatAnalysisSliceState {
  return {
    running: false,
    error: '',
    progressPercent: 0,
    progressStatus: '',
    progressEtaSec: 0,
  };
}

export function createLeadAuthSliceState(): LeadAuthSliceState {
  return {
    authLoading: false,
    authForm: {
      apiId: '',
      apiHash: '',
      phone: '',
      code: '',
      password: '',
    },
  };
}

export function createLlmAnswersSliceState(): LlmAnswersSliceState {
  return {
    llmRunning: false,
    llmHtml: '',
    llmProgress: {
      running: false,
      percent: 0,
      etaSec: 0,
      status: '',
      error: '',
    },
  };
}
