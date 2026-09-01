# MobX guidelines

## Observer components

Wrap every component that reads observable state in `observer()`.
Never combine `observer()` and `memo()` on the same component.

## Store construction

Call `makePersistable` after `makeAutoObservable` in a store constructor.

## Store boundaries

Never import another store's singleton directly - go through the root store.

## Keyed state

Use Observable Maps for keyed state.

## Readability

Keep stores small and readable.
