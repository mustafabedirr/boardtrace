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
    readonly id: string;
    sendMessage(message: unknown): Promise<unknown>;
    readonly onMessage: {
      addListener(
        listener: (
          message: unknown,
          sender: unknown,
          sendResponse: (response: unknown) => void,
        ) => boolean | void,
      ): void;
    };
  }

  interface Scripting {
    executeScript(injection: {
      readonly files: readonly string[];
      readonly target: { readonly tabId: number };
    }): Promise<void>;
  }

  interface Tabs {
    query(query: {
      readonly active: boolean;
      readonly currentWindow: boolean;
    }): Promise<readonly Tab[]>;
    sendMessage(tabId: number, message: unknown): Promise<void>;
  }

  interface StorageArea {
    get(key: string): Promise<Record<string, unknown>>;
    remove(key: string): Promise<void>;
    set(items: Record<string, unknown>): Promise<void>;
  }

  interface Storage {
    readonly session: StorageArea;
  }

  const action: Action;
  const runtime: Runtime;
  const scripting: Scripting;
  const storage: Storage;
  const tabs: Tabs;
}
