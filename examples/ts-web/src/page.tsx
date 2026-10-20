import { formatPrice } from "./index";

export default function Page() {
  return <p>{formatPrice(1999)}</p>;
}
