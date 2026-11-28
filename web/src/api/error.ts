export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly retryable: boolean;

  constructor(status: number, message: string, code?: string, retryable = false) {
    super(message);
    this.status = status;
    this.code = code;
    this.retryable = retryable;
  }
}
