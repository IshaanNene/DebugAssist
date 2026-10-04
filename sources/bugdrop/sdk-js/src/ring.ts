export class Ring<T> {
  private items: T[] = [];
  constructor(private readonly max: number) {}
  push(x: T) {
    this.items.push(x);
    if (this.items.length > this.max) this.items.shift();
  }
  toArray(): T[] {
    return [...this.items];
  }
  get size() {
    return this.items.length;
  }
}
