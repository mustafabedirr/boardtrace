declare namespace chrome {
  interface Tab {
    readonly id?: number;
  }

  interface Action {
    readonly onClicked: {
      addListener(listener: (tab: Tab) => void): void;
    };
  }

  interface Runtime {
    sendMessage(message: unknown): Promise<void>;
    readonly onMessage: {
      addListener(listener: (message: unknown) => void): void;
    };
  }

  interface Scripting {
    executeScript(injection: {
      readonly files: readonly string[];
      readonly target: { readonly tabId: number };
    }): Promise<void>;
  }

  interface Tabs {
    sendMessage(tabId: number, message: unknown): Promise<void>;
  }

  const action: Action;
  const runtime: Runtime;
  const scripting: Scripting;
  const tabs: Tabs;
}
