export const metadata = {
  title: "CARDEX | B2B Market",
  description: "Institutional Decision Desk",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body
        style={{
          backgroundColor: "#0a0a0a",
          color: "#e5e5e5",
          fontFamily: "monospace",
          margin: 0,
          padding: "20px",
        }}
      >
        {children}
      </body>
    </html>
  );
}
