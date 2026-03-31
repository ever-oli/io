import * as vscode from 'vscode';
import * as WebSocket from 'ws';

interface IOConfig {
    serverUrl: string;
    sessionId?: string;
}

interface SelectionData {
    file: string;
    text: string;
    startLine: number;
    endLine: number;
    startColumn: number;
    endColumn: number;
}

interface PendingChange {
    file: string;
    description: string;
    newContent: string;
}

export class IOClient {
    private ws: WebSocket | undefined;
    private config: IOConfig;
    private reconnectAttempts = 0;
    private maxReconnectAttempts = 5;

    constructor() {
        const workspaceConfig = vscode.workspace.getConfiguration('io');
        this.config = {
            serverUrl: workspaceConfig.get('serverUrl') || 'http://localhost:8642'
        };
    }

    async connect(): Promise<void> {
        return new Promise((resolve, reject) => {
            try {
                // Convert http to ws
                const wsUrl = this.config.serverUrl.replace(/^http/, 'ws') + '/ws';
                
                this.ws = new WebSocket(wsUrl);

                this.ws.on('open', () => {
                    console.log('IO: Connected to server');
                    this.reconnectAttempts = 0;
                    
                    // Send init message
                    this.ws?.send(JSON.stringify({
                        type: 'init',
                        client: 'vscode',
                        version: '0.1.0'
                    }));
                    
                    resolve();
                });

                this.ws.on('message', (data: WebSocket.Data) => {
                    this.handleMessage(data.toString());
                });

                this.ws.on('error', (error) => {
                    console.error('IO: WebSocket error', error);
                    reject(error);
                });

                this.ws.on('close', () => {
                    console.log('IO: Connection closed');
                    this.attemptReconnect();
                });

            } catch (error) {
                reject(error);
            }
        });
    }

    disconnect(): void {
        this.ws?.close();
        this.ws = undefined;
    }

    private attemptReconnect(): void {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = Math.pow(2, this.reconnectAttempts) * 1000;
            
            console.log(`IO: Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
            
            setTimeout(() => {
                this.connect().catch(console.error);
            }, delay);
        }
    }

    private handleMessage(data: string): void {
        try {
            const message = JSON.parse(data);
            
            switch (message.type) {
                case 'suggestion':
                    this.handleSuggestion(message);
                    break;
                case 'chat':
                    this.handleChatMessage(message);
                    break;
                case 'file_change':
                    this.handleFileChange(message);
                    break;
                default:
                    console.log('IO: Unknown message type', message.type);
            }
        } catch (error) {
            console.error('IO: Error parsing message', error);
        }
    }

    private handleSuggestion(message: any): void {
        // Show suggestion inline or in chat
        vscode.window.showInformationMessage(
            `IO Suggestion: ${message.text}`,
            'Apply',
            'Dismiss'
        ).then(selection => {
            if (selection === 'Apply') {
                this.applySuggestion(message);
            }
        });
    }

    private handleChatMessage(message: any): void {
        // This would update the chat view
        console.log('IO Chat:', message.text);
    }

    private handleFileChange(message: any): void {
        // Show notification about file changes
        vscode.window.showInformationMessage(
            `IO wants to modify ${message.file}`,
            'View Diff',
            'Apply',
            'Dismiss'
        ).then(selection => {
            if (selection === 'View Diff') {
                vscode.commands.executeCommand('io.showDiff');
            } else if (selection === 'Apply') {
                this.applyFileChange(message);
            }
        });
    }

    private async applySuggestion(message: any): Promise<void> {
        // Apply the suggestion to the current file
        const editor = vscode.window.activeTextEditor;
        if (!editor) return;

        await editor.edit(editBuilder => {
            const position = new vscode.Position(message.line, message.column);
            editBuilder.insert(position, message.text);
        });
    }

    private async applyFileChange(message: any): Promise<void> {
        const uri = vscode.Uri.file(message.file);
        const content = Buffer.from(message.content, 'utf8');
        await vscode.workspace.fs.writeFile(uri, content);
    }

    // Public methods for commands
    async explain(text: string, context: { file: string; line: number }): Promise<string> {
        return new Promise((resolve, reject) => {
            if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
                reject('Not connected to IO');
                return;
            }

            const requestId = Math.random().toString(36).substring(7);
            
            const handler = (data: WebSocket.Data) => {
                const response = JSON.parse(data.toString());
                if (response.requestId === requestId) {
                    this.ws?.off('message', handler);
                    resolve(response.explanation);
                }
            };

            this.ws.on('message', handler);
            
            this.ws.send(JSON.stringify({
                type: 'explain',
                requestId,
                text,
                context
            }));

            // Timeout after 30 seconds
            setTimeout(() => {
                this.ws?.off('message', handler);
                reject('Request timeout');
            }, 30000);
        });
    }

    async fix(text: string, context: { file: string; line: number }): Promise<string> {
        return new Promise((resolve, reject) => {
            if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
                reject('Not connected to IO');
                return;
            }

            const requestId = Math.random().toString(36).substring(7);
            
            const handler = (data: WebSocket.Data) => {
                const response = JSON.parse(data.toString());
                if (response.requestId === requestId) {
                    this.ws?.off('message', handler);
                    resolve(response.fix);
                }
            };

            this.ws.on('message', handler);
            
            this.ws.send(JSON.stringify({
                type: 'fix',
                requestId,
                text,
                context
            }));

            setTimeout(() => {
                this.ws?.off('message', handler);
                reject('Request timeout');
            }, 30000);
        });
    }

    async syncSelection(selection: SelectionData): Promise<void> {
        this.ws?.send(JSON.stringify({
            type: 'selection',
            ...selection
        }));
    }

    async getPendingChanges(): Promise<PendingChange[]> {
        return new Promise((resolve, reject) => {
            if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
                reject('Not connected');
                return;
            }

            const requestId = Math.random().toString(36).substring(7);
            
            const handler = (data: WebSocket.Data) => {
                const response = JSON.parse(data.toString());
                if (response.requestId === requestId) {
                    this.ws?.off('message', handler);
                    resolve(response.changes || []);
                }
            };

            this.ws.on('message', handler);
            
            this.ws.send(JSON.stringify({
                type: 'get_pending_changes',
                requestId
            }));

            setTimeout(() => {
                this.ws?.off('message', handler);
                resolve([]);
            }, 5000);
        });
    }

    sendChat(message: string): void {
        this.ws?.send(JSON.stringify({
            type: 'chat',
            message
        }));
    }
}
