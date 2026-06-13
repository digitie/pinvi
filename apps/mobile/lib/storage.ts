import AsyncStorage from '@react-native-async-storage/async-storage';
import type { StateStorage } from 'zustand/middleware';

/**
 * zustand persist용 AsyncStorage 어댑터.
 * 웹은 localStorage, 모바일은 AsyncStorage를 주입한다 (frontend.md §4.4).
 */
export const asyncStorageAdapter: StateStorage = {
  getItem: (name) => AsyncStorage.getItem(name),
  setItem: (name, value) => AsyncStorage.setItem(name, value),
  removeItem: (name) => AsyncStorage.removeItem(name),
};
