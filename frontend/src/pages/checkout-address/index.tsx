import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ChevronRight, MapPin, Navigation, Plus, AlertCircle } from "lucide-react";
import { useAsync } from "@/hooks/useAsync";
import * as ordersApi from "@/api/orders";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { useCheckoutStore } from "@/store/checkoutStore";
import { ApiError } from "@/lib/api";

const schema = z.object({
  label: z.string().min(1, "Libellé requis"),
  street: z.string().min(1, "Adresse requise"),
  city: z.string().min(1, "Ville requise"),
  country: z.string().min(1, "Pays requis"),
});
type FormValues = z.infer<typeof schema>;

export default function CheckoutAddressPage() {
  const navigate = useNavigate();
  const items = useCheckoutStore((s) => s.items);
  const setAddress = useCheckoutStore((s) => s.setAddress);
  const { data: addresses, loading, error: loadError, refetch: refetchAddresses } = useAsync(() => ordersApi.listAddresses(), []);
  const [showForm, setShowForm] = useState(false);
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [locating, setLocating] = useState(false);
  const [locationError, setLocationError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { country: "Sénégal" } });

  if (items.length === 0) return <Navigate to="/cart" replace />;

  function captureLocation() {
    if (!navigator.geolocation) {
      setLocationError("Localisation non disponible sur cet appareil.");
      return;
    }
    setLocating(true);
    setLocationError(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setCoords({
          lat: Number(pos.coords.latitude.toFixed(6)),
          lng: Number(pos.coords.longitude.toFixed(6)),
        });
        setLocating(false);
      },
      () => {
        setLocationError("Localisation refusée ou indisponible.");
        setLocating(false);
      },
    );
  }

  async function onCreate(values: FormValues) {
    setSubmitError(null);
    try {
      const address = await ordersApi.createAddress({
        ...values,
        ...(coords ? { latitude: coords.lat, longitude: coords.lng } : {}),
      });
      setAddress(address);
      navigate("/checkout-delivery");
    } catch (err) {
      if (err instanceof ApiError) {
        const data = err.data as Record<string, unknown> | null;
        if (typeof data?.detail === "string") {
          setSubmitError(data.detail);
        } else if (data && typeof data === "object") {
          const firstError = Object.values(data)[0];
          setSubmitError(Array.isArray(firstError) ? String(firstError[0]) : "Adresse invalide.");
        } else {
          setSubmitError(`Impossible d'enregistrer l'adresse (${err.status}).`);
        }
      } else {
        setSubmitError("Impossible de contacter le serveur. Vérifiez votre connexion.");
      }
    }
  }

  function choose(addressId: string) {
    const address = addresses?.find((a) => a.id === addressId);
    if (address) {
      setAddress(address);
      navigate("/checkout-delivery");
    }
  }

  if (loading) return <Spinner label="Chargement de vos adresses…" />;

  return (
    <div className="flex flex-col gap-6">
      <h1 className="flex items-center gap-2 font-display text-2xl font-bold text-gray-900">
        <MapPin className="h-6 w-6 text-orange" />
        Adresse de livraison
      </h1>

      {loadError && (
        <div
          role="alert"
          className="flex items-start gap-2.5 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <div className="flex flex-1 flex-col gap-1">
            <span>Impossible de charger vos adresses.</span>
            <button
              type="button"
              onClick={refetchAddresses}
              className="self-start font-semibold text-red-700 underline underline-offset-2"
            >
              Réessayer
            </button>
          </div>
        </div>
      )}

      {submitError && (
        <div
          role="alert"
          className="flex items-start gap-2.5 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{submitError}</span>
        </div>
      )}

      {addresses && addresses.length > 0 && !showForm && (
        <div className="flex flex-col gap-3">
          {addresses.map((address) => (
            <button key={address.id} onClick={() => choose(address.id)} className="text-left">
              <Card variant="interactive" className="flex items-center justify-between">
                <div>
                  <p className="font-semibold text-ink">{address.label}</p>
                  <p className="text-sm text-muted-foreground">
                    {address.street}, {address.city}, {address.country}
                  </p>
                </div>
                <ChevronRight className="h-5 w-5 shrink-0 text-muted-foreground" />
              </Card>
            </button>
          ))}
          <button
            onClick={() => setShowForm(true)}
            className="focus-ring flex items-center gap-1.5 self-start rounded-md text-sm font-semibold text-orange transition-colors hover:text-orange-dark"
          >
            <Plus className="h-4 w-4" /> Ajouter une nouvelle adresse
          </button>
        </div>
      )}

      {(showForm || !addresses || addresses.length === 0) && (
        <Card>
          <form onSubmit={handleSubmit(onCreate)} className="flex flex-col gap-4">
            <Input label="Libellé (Maison, Bureau…)" {...register("label")} error={errors.label?.message} />
            <Input label="Adresse" {...register("street")} error={errors.street?.message} />
            <div className="grid grid-cols-2 gap-4">
              <Input label="Ville" {...register("city")} error={errors.city?.message} />
              <Input label="Pays" {...register("country")} error={errors.country?.message} />
            </div>

            <div>
              <Button type="button" variant="secondary" size="sm" onClick={captureLocation} loading={locating}>
                <Navigation className="h-4 w-4" />
                {coords ? "Position enregistrée ✓" : "Utiliser ma position actuelle"}
              </Button>
              <p className="mt-1.5 text-xs text-muted-foreground">
                {coords
                  ? "Le livreur et vous pourrez suivre la livraison sur une carte."
                  : locationError ?? "Optionnel : permet d'afficher une carte pendant la livraison."}
              </p>
            </div>

            <Button type="submit" loading={isSubmitting} className="mt-2">
              Enregistrer et continuer
            </Button>
          </form>
        </Card>
      )}
    </div>
  );
}
