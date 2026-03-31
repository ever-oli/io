import * as vscode from 'vscode';
import { IOClient } from './ioClient';
import { ChatViewProvider } from './chatViewProvider';
import { SelectionSync } from './selectionSync';
import { InlineDecorations } from './inlineDecorations';

let ioClient: IOClient | undefined;
let chatProvider: ChatViewProvider | undefined;
let selectionSync: SelectionSync | undefined;
let inlineDecorations: InlineDecorations | undefined;

export function activate(context: vscode.ExtensionContext) {
    console.log('IO extension activated');

    // Initialize IO client
    ioClient = new IOClient();
    
    // Initialize providers
    chatProvider = new ChatViewProvider(context.extensionUri, ioClient);
    selectionSync = new SelectionSync(ioClient);
    inlineDecorations = new InlineDecorations();

    // Register chat view
    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider('io.chatView', chatProvider)
    );

    // Register commands
    context.subscriptions.push(
        vscode.commands.registerCommand('io.start', async () => {
            try {
                await ioClient?.connect();
                vscode.window.showInformationMessage('IO: Connected successfully');
                vscode.commands.executeCommand('setContext', 'io.connected', true);
            } catch (error) {
                vscode.window.showErrorMessage(`IO: Failed to connect - ${error}`);
            }
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('io.stop', async () => {
            await ioClient?.disconnect();
            vscode.commands.executeCommand('setContext', 'io.connected', false);
            vscode.window.showInformationMessage('IO: Disconnected');
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('io.explain', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) return;

            const selection = editor.selection;
            const text = editor.document.getText(selection);
            
            if (!text) {
                vscode.window.showWarningMessage('IO: Please select code to explain');
                return;
            }

            try {
                const explanation = await ioClient?.explain(text, {
                    file: editor.document.fileName,
                    line: selection.start.line
                });
                
                if (explanation) {
                    chatProvider?.showMessage('IO', explanation);
                }
            } catch (error) {
                vscode.window.showErrorMessage(`IO: ${error}`);
            }
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('io.fix', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) return;

            const selection = editor.selection;
            const text = editor.document.getText(selection);
            
            if (!text) {
                vscode.window.showWarningMessage('IO: Please select code to fix');
                return;
            }

            try {
                const fix = await ioClient?.fix(text, {
                    file: editor.document.fileName,
                    line: selection.start.line
                });
                
                if (fix) {
                    // Show diff
                    const originalUri = editor.document.uri;
                    const modifiedUri = originalUri.with({ scheme: 'io', path: originalUri.path + '.fixed' });
                    
                    await vscode.commands.executeCommand(
                        'vscode.diff',
                        originalUri,
                        modifiedUri,
                        'IO Suggested Fix'
                    );
                }
            } catch (error) {
                vscode.window.showErrorMessage(`IO: ${error}`);
            }
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('io.chat', () => {
            vscode.commands.executeCommand('io.chatView.focus');
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('io.syncSelection', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) return;

            const selection = editor.selection;
            const text = editor.document.getText(selection);
            
            if (!text) {
                vscode.window.showWarningMessage('IO: No selection to sync');
                return;
            }

            await ioClient?.syncSelection({
                file: editor.document.fileName,
                text: text,
                startLine: selection.start.line,
                endLine: selection.end.line,
                startColumn: selection.start.character,
                endColumn: selection.end.character
            });

            vscode.window.showInformationMessage('IO: Selection synced');
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('io.showDiff', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) return;

            // This would show pending IO changes
            const changes = await ioClient?.getPendingChanges();
            if (changes && changes.length > 0) {
                // Show first change
                const change = changes[0];
                const originalContent = await vscode.workspace.fs.readFile(vscode.Uri.file(change.file));
                const modifiedContent = Buffer.from(change.newContent);
                
                // Create temporary files for diff
                const originalUri = vscode.Uri.parse(`io-diff://original/${change.file}`);
                const modifiedUri = vscode.Uri.parse(`io-diff://modified/${change.file}`);
                
                // Register content provider
                const provider = new class implements vscode.TextDocumentContentProvider {
                    provideTextDocumentContent(uri: vscode.Uri): string {
                        if (uri.scheme === 'io-diff') {
                            return uri.path.includes('original') 
                                ? originalContent.toString() 
                                : modifiedContent.toString();
                        }
                        return '';
                    }
                };
                
                context.subscriptions.push(
                    vscode.workspace.registerTextDocumentContentProvider('io-diff', provider)
                );
                
                await vscode.commands.executeCommand(
                    'vscode.diff',
                    originalUri,
                    modifiedUri,
                    `IO: ${change.description}`
                );
            } else {
                vscode.window.showInformationMessage('IO: No pending changes');
            }
        })
    );

    // Handle selection changes
    context.subscriptions.push(
        vscode.window.onDidChangeTextEditorSelection((event) => {
            const config = vscode.workspace.getConfiguration('io');
            if (config.get('autoSync')) {
                selectionSync?.sync(event.textEditor, event.selections[0]);
            }
        })
    );

    // Auto-connect if configured
    const config = vscode.workspace.getConfiguration('io');
    if (config.get('autoConnect')) {
        vscode.commands.executeCommand('io.start');
    }
}

export function deactivate() {
    ioClient?.disconnect();
    console.log('IO extension deactivated');
}
