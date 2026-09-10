export type LeadStoreCoreState = {
  selectedLeadName: string;
  loading: boolean;
  error: string;
};

export function createLeadStoreCoreState(): LeadStoreCoreState {
  return {
    selectedLeadName: '',
    loading: false,
    error: '',
  };
}
