'use client';
import { ThemeToggle } from '@/components/theme/theme-toggle';
import {
  DataValue,
  MetricCard,
  MoveQualityBadge,
  StatusBadge,
} from '@/components/design-system/primitives';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
export default function DesignSystemPage() {
  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-6xl px-5 py-10">
        <header className="flex items-center justify-between border-b pb-6">
          <div>
            <p className="text-sm text-secondary">BoardTrace</p>
            <h1 className="text-2xl font-semibold">Design system foundation</h1>
            <p className="text-sm text-muted-foreground">Review every decision.</p>
          </div>
          <ThemeToggle />
        </header>
        <div className="space-y-10 py-10">
          <section>
            <p className="text-xs uppercase tracking-widest text-secondary">Identity</p>
            <h2 className="mt-2 text-3xl font-bold">Precision Analytics + Modern Chess</h2>
            <p className="mt-3 max-w-2xl text-muted-foreground">
              A calm, professional interface for post-game review, never live assistance.
            </p>
          </section>
          <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard label="Default radius" value="8 px" helper="Controlled geometry" />
            <MetricCard label="Motion" value="220 ms" helper="Reduced motion aware" />
            <MetricCard label="Contrast" value="AA" helper="WCAG 2.2 target" />
            <MetricCard label="Data" value="Mono" helper="Tabular numbers" />
          </section>
          <Tabs defaultValue="actions">
            <TabsList>
              <TabsTrigger value="actions">Actions</TabsTrigger>
              <TabsTrigger value="states">States</TabsTrigger>
            </TabsList>
            <TabsContent value="actions" className="mt-4 space-y-4">
              <div className="flex flex-wrap gap-3">
                <Button>Primary action</Button>
                <Button variant="secondary">Secondary</Button>
                <Dialog>
                  <DialogTrigger asChild>
                    <Button variant="outline">Open dialog</Button>
                  </DialogTrigger>
                  <DialogContent>
                    <DialogHeader>
                      <DialogTitle>Foundation dialog</DialogTitle>
                    </DialogHeader>
                    <p>Focus stays within the dialog.</p>
                  </DialogContent>
                </Dialog>
              </div>
              <div className="flex gap-3">
                <Switch id="sample" />
                <label htmlFor="sample">Review preference</label>
                <Input aria-label="Sample input" placeholder="Input token" />
              </div>
            </TabsContent>
            <TabsContent value="states" className="mt-4">
              <div className="flex flex-wrap gap-2">
                {(
                  [
                    'ready',
                    'capturing',
                    'processing',
                    'waiting',
                    'completed',
                    'locked',
                    'failed',
                    'low-confidence',
                  ] as const
                ).map((x) => (
                  <StatusBadge key={x} status={x} />
                ))}
                {(
                  [
                    'best',
                    'excellent',
                    'good',
                    'book',
                    'inaccuracy',
                    'mistake',
                    'blunder',
                    'forced',
                    'unknown',
                  ] as const
                ).map((x) => (
                  <MoveQualityBadge key={x} quality={x} />
                ))}
              </div>
            </TabsContent>
          </Tabs>
          <section className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Chessboard colors</CardTitle>
              </CardHeader>
              <CardContent className="grid grid-cols-4 overflow-hidden rounded-md border">
                {Array.from({ length: 16 }, (_, i) => (
                  <div
                    key={i}
                    className={`aspect-square ${(i + Math.floor(i / 4)) % 2 === 0 ? 'bg-board-light' : 'bg-board-dark'}`}
                  />
                ))}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Feedback</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <Alert>
                  <AlertTitle>Analysis remains locked</AlertTitle>
                  <AlertDescription>
                    Results appear only after verified completion.
                  </AlertDescription>
                </Alert>
                <Progress value={62} />
                <Skeleton className="h-8 w-full" />
                <p>
                  <DataValue tone="positive">+1.24</DataValue>
                </p>
              </CardContent>
            </Card>
          </section>
        </div>
      </div>
    </main>
  );
}
