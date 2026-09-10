import { CHAT_PROMPT_DEFAULTS, type ChatPromptConfig } from './utils';

export type LeadStorePromptsState = {
  prompts: ChatPromptConfig[];
  page: number;
  pageSize: number;
};

export function createLeadStorePromptsState(): LeadStorePromptsState {
  return {
    prompts: CHAT_PROMPT_DEFAULTS.map((prompt) => ({ ...prompt })),
    page: 1,
    pageSize: 5,
  };
}
