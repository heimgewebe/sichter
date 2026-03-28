export interface ObservatoryViewData {
  title: string;
  [key: string]: unknown;
}

export async function getObservatoryData(): Promise<ObservatoryViewData> {
  // Placeholder – extend when observatory artifact is defined.
  return {
    title: 'Observatorium',
  };
}
