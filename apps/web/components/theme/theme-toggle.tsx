'use client';
import { Laptop, Moon, Sun } from 'lucide-react';
import { useTheme } from 'next-themes';
import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
export function ThemeToggle() {
  const [mounted, setMounted] = useState(false);
  const { setTheme, theme } = useTheme();
  useEffect(() => setMounted(true), []);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button aria-label="Change theme" variant="outline" size="icon">
          {theme === 'light' ? <Sun /> : theme === 'dark' ? <Moon /> : <Laptop />}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuRadioGroup value={mounted ? theme : 'system'} onValueChange={setTheme}>
          <DropdownMenuRadioItem value="light">Light</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="dark">Dark</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="system">System</DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
