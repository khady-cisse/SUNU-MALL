import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="grid min-h-screen place-items-center bg-background p-6">
          <div className="max-w-md rounded-2xl border border-border bg-white p-8 text-center">
            <h1 className="mt-3 font-display text-xl font-bold text-gray-900">Oups, un problème est survenu</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              Une erreur inattendue a interrompu l'affichage. Rechargez la page pour continuer.
            </p>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="mt-5 rounded-xl bg-orange px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-orange-600"
            >
              Recharger la page
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}