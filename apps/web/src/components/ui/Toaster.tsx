'use client'
import * as Toast from '@radix-ui/react-toast'
export function Toaster() {
  return (
    <Toast.Provider swipeDirection="right">
      <Toast.Viewport className="fixed bottom-4 right-4 z-[100] flex max-w-sm flex-col gap-2" />
    </Toast.Provider>
  )
}
